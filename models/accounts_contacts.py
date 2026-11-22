from datetime import datetime

from db.batch_queries import execute_in_batches, insert_rows
from db.mysql_connection import open_connection

def delete_lost_contacts_for_accounts(account_id: int, contact_ids: list[int]) -> None:
    """
    Delete all links between the account and the contacts that are NOT in the list provided.

    account_id -- internal id of the account that's being updated
    contact_ids -- internal ids (contacts.id) of all contacts that are currently visible for the account
    """
    # Compute the lost contacts in python: running `NOT IN (batch)` once per batch would delete
    # the links belonging to every other batch.
    visible_contact_ids = set(contact_ids)
    lost_contact_ids = [
        contact_id
        for contact_id in get_contact_from_account_ids(account_id)
        if contact_id not in visible_contact_ids
    ]
    with open_connection() as conn:
        execute_in_batches(
            conn.cursor(),
            "DELETE FROM accounts_contacts WHERE `account_id` = %s AND `contact_id` IN ({ids})",
            lost_contact_ids,
            [account_id],
        )

def upsert_accounts_contacts_connections(account_id: int, contact_ids: list[int]) -> None:
    """
    Insert all new conection between an account and a contact and update all the already existing ones

    account_id -- internal id of the account that's being updated
    contact_ids -- internal ids (contacts.id) of all contacts that are currently visible for the account
    """
    now = datetime.now()
    with open_connection() as conn:
        insert_rows(
            conn.cursor(),
            "accounts_contacts",
            ["account_id", "contact_id", "created_at", "updated_at"],
            [[account_id, contact_id, now, now] for contact_id in contact_ids],
            update_columns=["updated_at"],
        )

def get_contact_from_account_ids(account_id: int) -> list[int]:
    """
    Get the list of all internal contact ids related to the given account_id

    account_id -- internal id of the account from wich we want to get the data
    Returns:
    internal_contact_ids -- list of all internal contact ids
    """
    sql = '''
    SELECT contact_id
    FROM accounts_contacts
    WHERE `account_id` = %s
    '''
    with open_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(sql, [account_id])
        return [row[0] for row in cursor.fetchall()]
