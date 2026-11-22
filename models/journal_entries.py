from datetime import date, datetime

from db.batch_queries import execute_in_batches, insert_rows
from db.mysql_connection import open_connection

# The functions used by the sync take a cursor as first argument: the sync writes the entries and their
# lines of a page in a single transaction. The functions used by the api open their own connection.

# Columns returned by the api: the internal ids are replaced by the odoo ids
ENTRY_COLUMNS = '''
    je.db, je.move_id, je.name, je.ref, je.date, je.state, je.move_type,
    j.journal_id, j.code AS journal_code, j.name AS journal_name,
    je.partner_odoo_id, je.currency, je.amount_total, je.odoo_write_date, je.created_at, je.updated_at
'''

def upsert_journal_entries(cursor, formated_entries: list[dict]) -> dict[int, int]:
    """
    Insert all new journal entries and update all existing ones

    cursor -- database cursor to use
    formated_entries -- list of journal entries informations to store in the database (all from the same db)
    Returns:
    internal_ids_by_move_id -- dictionary {odoo move id: internal journal entry id}
    """
    now = datetime.now()
    insert_rows(
        cursor,
        "journal_entries",
        ["db", "move_id", "journal_id", "name", "ref", "date", "state", "move_type",
         "partner_odoo_id", "currency", "amount_total", "odoo_write_date", "created_at", "updated_at"],
        [
            [entry['db'], entry['move_id'], entry['journal_id'], entry['name'], entry['ref'], entry['date'],
             entry['state'], entry['move_type'], entry['partner_odoo_id'], entry['currency'],
             entry['amount_total'], entry['odoo_write_date'], now, now]
            for entry in formated_entries
        ],
        update_columns=["journal_id", "name", "ref", "date", "state", "move_type", "partner_odoo_id", "currency",
                        "amount_total", "odoo_write_date", "updated_at"],
    )
    if not formated_entries:
        return {}
    return get_internal_ids_by_move_id(cursor, formated_entries[0]['db'], [entry['move_id'] for entry in formated_entries])

def get_stored_write_dates(cursor, db: str, move_ids: list[int]) -> dict[int, str]:
    """
    Get the odoo write_date stored for the provided journal entries, to detect the ones that changed in odoo

    cursor -- database cursor to use
    db -- name of the database in odoo systems
    move_ids -- list of odoo move ids
    Returns:
    write_dates_by_move_id -- dictionary {odoo move id: odoo write_date as 'YYYY-MM-DD HH:MM:SS'}, only for stored entries
    """
    rows = execute_in_batches(
        cursor,
        "SELECT move_id, odoo_write_date FROM journal_entries WHERE `db` = %s AND `move_id` IN ({ids})",
        move_ids,
        [db],
    )
    return {move_id: write_date.strftime("%Y-%m-%d %H:%M:%S") for move_id, write_date in rows}

def get_internal_ids_by_move_id(cursor, db: str, move_ids: list[int]) -> dict[int, int]:
    """
    Map odoo move ids to the internal journal entry ids

    cursor -- database cursor to use
    db -- name of the database in odoo systems
    move_ids -- list of odoo move ids
    Returns:
    internal_ids_by_move_id -- dictionary {odoo move id: internal journal entry id}
    """
    rows = execute_in_batches(
        cursor,
        "SELECT move_id, id FROM journal_entries WHERE `db` = %s AND `move_id` IN ({ids})",
        move_ids,
        [db],
    )
    return {move_id: internal_id for move_id, internal_id in rows}

def replace_journal_entry_lines(cursor, journal_entry_ids: list[int], formated_lines: list[dict]) -> None:
    """
    Replace all the lines of the provided journal entries by the provided lines.
    The lines of an entry are always refreshed together with their entry, so replacing them is simpler and
    safer than diffing them (it also removes the lines deleted in odoo).

    cursor -- database cursor to use
    journal_entry_ids -- internal ids of the journal entries whose lines are replaced
    formated_lines -- the new lines of those journal entries
    """
    execute_in_batches(cursor, "DELETE FROM journal_entry_lines WHERE `journal_entry_id` IN ({ids})", journal_entry_ids)
    now = datetime.now()
    insert_rows(
        cursor,
        "journal_entry_lines",
        ["journal_entry_id", "line_id", "account_code", "account_name", "label", "partner_odoo_id",
         "debit", "credit", "balance", "amount_currency", "currency", "date", "created_at", "updated_at"],
        [
            [line['journal_entry_id'], line['line_id'], line['account_code'], line['account_name'], line['label'],
             line['partner_odoo_id'], line['debit'], line['credit'], line['balance'], line['amount_currency'],
             line['currency'], line['date'], now, now]
            for line in formated_lines
        ],
    )

def delete_lost_journal_entries(cursor, db: str, journal_ids: list[int], existing_move_ids: list[int]) -> int:
    """
    Delete the journal entries of the provided journals that do not exist in odoo anymore (their lines are
    deleted by the ON DELETE CASCADE).
    Only the journals visible for the synced account are checked: the entries of other journals may be visible
    for other accounts and are checked when those accounts are synced.

    cursor -- database cursor to use
    db -- name of the database in odoo systems
    journal_ids -- internal ids of the journals visible for the synced account
    existing_move_ids -- odoo ids of all journal entries currently visible in odoo for the synced account
    Returns:
    deleted -- number of deleted journal entries
    """
    stored = execute_in_batches(
        cursor,
        "SELECT id, move_id FROM journal_entries WHERE `db` = %s AND `journal_id` IN ({ids})",
        journal_ids,
        [db],
    )
    existing = set(existing_move_ids)
    lost_ids = [internal_id for internal_id, move_id in stored if move_id not in existing]
    execute_in_batches(cursor, "DELETE FROM journal_entries WHERE `id` IN ({ids})", lost_ids)
    return len(lost_ids)

def get_journal_entries_for_account_id(account_id: int, limit: int, offset: int, journal_id: int,
                                       date_from: date | None = None, date_to: date | None = None) -> tuple[list[dict], int]:
    """
    Get one page of the journal entries of a journal visible for the account, ordered by odoo id

    account_id -- internal id of the account from which we want to get the data
    limit -- maximum number of entries to return
    offset -- number of entries to skip
    journal_id -- odoo id of the journal whose entries are returned
    date_from -- only return the entries dated on or after this date
    date_to -- only return the entries dated on or before this date
    Returns:
    journal_entries -- list of dictionaries containing the journal entries data (without their lines)
    total -- number of journal entries matching the filters
    """
    conditions = ["aj.account_id = %s", "j.journal_id = %s"]
    params = [account_id, journal_id]
    if date_from is not None:
        conditions.append("je.date >= %s")
        params.append(date_from)
    if date_to is not None:
        conditions.append("je.date <= %s")
        params.append(date_to)
    from_where = f'''
        FROM journal_entries AS je
        INNER JOIN journals AS j ON j.id = je.journal_id
        INNER JOIN accounts_journals AS aj ON aj.journal_id = j.id
        WHERE {" AND ".join(conditions)}
    '''
    with open_connection() as conn:
        cursor = conn.cursor(dictionary=True)
        cursor.execute(f"SELECT {ENTRY_COLUMNS} {from_where} ORDER BY je.move_id LIMIT %s OFFSET %s", [*params, limit, offset])
        journal_entries = cursor.fetchall()
        cursor.execute(f"SELECT count(*) AS total {from_where}", params)
        total = cursor.fetchone()["total"]
    return journal_entries, total

def get_journal_entry_from_account_id_move_id(account_id: int, move_id: int) -> dict | None:
    """
    Get one journal entry with its lines by its odoo id, only if it is visible for the account (through its journal)

    account_id -- internal id of the account from which we want to get the data
    move_id -- odoo id of the journal entry
    Returns:
    journal_entry -- dictionary containing the journal entry data and its lines, or None if the account cannot see it
    """
    with open_connection() as conn:
        cursor = conn.cursor(dictionary=True)
        cursor.execute(f'''
            SELECT je.id AS internal_id, {ENTRY_COLUMNS}
            FROM journal_entries AS je
            INNER JOIN journals AS j ON j.id = je.journal_id
            INNER JOIN accounts_journals AS aj ON aj.journal_id = j.id
            WHERE aj.account_id = %s
                AND je.move_id = %s
        ''', [account_id, move_id])
        journal_entry = cursor.fetchone()
        if journal_entry is not None:
            cursor.execute('''
                SELECT line_id, account_code, account_name, label, partner_odoo_id,
                    debit, credit, balance, amount_currency, currency, date
                FROM journal_entry_lines
                WHERE journal_entry_id = %s
                ORDER BY line_id
            ''', [journal_entry.pop("internal_id")])
            journal_entry["lines"] = cursor.fetchall()
    return journal_entry
