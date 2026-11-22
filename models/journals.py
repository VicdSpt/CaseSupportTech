from datetime import datetime

from db.batch_queries import execute_in_batches, insert_rows
from db.mysql_connection import open_connection

def upsert_journals(db: str, formated_journals: list[dict], journal_db_ids: list[int]) -> list[int]:
    """
    Upsert the provided list of journals by:
    - inserting all new journals
    - updating all existing journals

    db -- odoo database related to the fetched journals
    formated_journals -- list containing all journal informations
    journal_db_ids -- list containing all odoo ids related to the fetched journals
    Returns:
    internal_journal_ids -- list of the internal ids of all upserted journals
    """
    # Step 1, upsert all journals informations
    __upsert_journals(formated_journals)
    # Step 2, get the list of internal ids of all upserted journals
    return __get_internal_journal_ids(db, journal_db_ids)

def __upsert_journals(formated_journals: list[dict]) -> None:
    """
    Insert all new journals and update all existing journals in the journals table

    formated_journals -- list of journals informations to store in the database
    """
    now = datetime.now()
    with open_connection() as conn:
        insert_rows(
            conn.cursor(),
            "journals",
            ["db", "journal_id", "name", "code", "type", "currency", "company", "active", "created_at", "updated_at"],
            [
                [journal['db'], journal['journal_id'], journal['name'], journal['code'], journal['type'],
                 journal['currency'], journal['company'], journal['active'], now, now]
                for journal in formated_journals
            ],
            update_columns=["name", "code", "type", "currency", "company", "active", "updated_at"],
        )

def __get_internal_journal_ids(db: str, journal_db_ids: list[int]) -> list[int]:
    """
    Get all internal ids from the upserted journals in the given odoo db

    db -- name of the database in odoo systems
    journal_db_ids -- list of odoo internal journal ids
    Returns:
    internal_journal_ids -- list of the internal ids of all upserted journals
    """
    with open_connection() as conn:
        rows = execute_in_batches(
            conn.cursor(),
            "SELECT id FROM journals WHERE `db` = %s AND `journal_id` IN ({ids})",
            journal_db_ids,
            [db],
        )
    return [row[0] for row in rows]

def get_journals_for_account_id(account_id: int, limit: int, offset: int) -> tuple[list[dict], int]:
    """
    Get one page of the journals visible for the given account, ordered by odoo id, formatted for the endpoint

    account_id -- internal id of the account from which we want to get the data
    limit -- maximum number of journals to return
    offset -- number of journals to skip
    Returns:
    journals -- list of dictionaries containing journals data
    total -- number of journals visible for the account
    """
    with open_connection() as conn:
        cursor = conn.cursor(dictionary=True)
        cursor.execute('''
            SELECT j.*
            FROM journals AS j
            INNER JOIN accounts_journals AS aj ON aj.journal_id = j.id
            WHERE aj.account_id = %s
            ORDER BY j.journal_id
            LIMIT %s OFFSET %s
        ''', [account_id, limit, offset])
        journals = cursor.fetchall()
        cursor.execute("SELECT count(*) AS total FROM accounts_journals WHERE account_id = %s", [account_id])
        total = cursor.fetchone()["total"]
    for journal in journals:
        journal.pop("id")
        journal["active"] = bool(journal["active"])
    return journals, total

def get_journal_from_account_id_journal_id(account_id: int, journal_id: int) -> dict | None:
    """
    Get one journal by its odoo id, only if it is visible for the given account

    account_id -- internal id of the account from which we want to get the data
    journal_id -- odoo id of the journal
    Returns:
    journal -- dictionary containing the journal data, or None if the account cannot see it
    """
    sql = '''
        SELECT j.*
        FROM journals AS j
        INNER JOIN accounts_journals AS aj ON aj.journal_id = j.id
        WHERE aj.account_id = %s
            AND j.journal_id = %s
    '''
    with open_connection() as conn:
        cursor = conn.cursor(dictionary=True)
        cursor.execute(sql, [account_id, journal_id])
        journal = cursor.fetchone()
    if journal is not None:
        journal.pop("id")
        journal["active"] = bool(journal["active"])
    return journal

def get_internal_journal_ids_by_odoo_id(cursor, db: str, journal_db_ids: list[int]) -> dict[int, int]:
    """
    Map odoo journal ids to the internal journal ids, using the provided cursor (so it can be part of a transaction)

    cursor -- database cursor to use
    db -- name of the database in odoo systems
    journal_db_ids -- list of odoo journal ids
    Returns:
    internal_ids_by_odoo_id -- dictionary {odoo journal id: internal journal id}
    """
    rows = execute_in_batches(
        cursor,
        "SELECT journal_id, id FROM journals WHERE `db` = %s AND `journal_id` IN ({ids})",
        list(set(journal_db_ids)),
        [db],
    )
    return {odoo_id: internal_id for odoo_id, internal_id in rows}
