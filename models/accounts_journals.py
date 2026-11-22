from datetime import datetime

from db.batch_queries import execute_in_batches, insert_rows
from db.mysql_connection import open_connection

def delete_lost_journals_for_account(account_id: int, journal_ids: list[int]) -> None:
    """
    Delete all links between the account and the journals that are NOT in the list provided.

    account_id -- internal id of the account that's being updated
    journal_ids -- internal ids (journals.id) of all journals that are currently visible for the account
    """
    visible_journal_ids = set(journal_ids)
    lost_journal_ids = [
        journal_id
        for journal_id in get_journals_from_account_id(account_id)
        if journal_id not in visible_journal_ids
    ]
    with open_connection() as conn:
        execute_in_batches(
            conn.cursor(),
            "DELETE FROM accounts_journals WHERE `account_id` = %s AND `journal_id` IN ({ids})",
            lost_journal_ids,
            [account_id],
        )

def upsert_accounts_journals_connections(account_id: int, journal_ids: list[int]) -> None:
    """
    Insert all new connections between an account and a journal and update all the already existing ones

    account_id -- internal id of the account that's being updated
    journal_ids -- internal ids (journals.id) of all journals that are currently visible for the account
    """
    now = datetime.now()
    with open_connection() as conn:
        insert_rows(
            conn.cursor(),
            "accounts_journals",
            ["account_id", "journal_id", "created_at", "updated_at"],
            [[account_id, journal_id, now, now] for journal_id in journal_ids],
            update_columns=["updated_at"],
        )

def get_journals_from_account_id(account_id: int) -> list[int]:
    """
    Get the list of all internal journal ids related to the given account_id

    account_id -- internal id of the account from which we want to get the data
    Returns:
    internal_journal_ids -- list of all internal journal ids
    """
    sql = '''
        SELECT journal_id
        FROM accounts_journals
        WHERE `account_id` = %s
    '''
    with open_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(sql, [account_id])
        return [row[0] for row in cursor.fetchall()]
