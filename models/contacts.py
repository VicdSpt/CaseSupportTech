from datetime import datetime

from db.batch_queries import execute_in_batches, insert_rows
from db.mysql_connection import open_connection

def upsert_contacts(db: str, formated_contacts: list[dict], contact_db_ids: list[int]) -> list[int]:
    """
    Upsert the provided list of contact by:
    - inserting all new contacts
    - updating all existing contacts

    db -- odoo database related to the fetched contacts
    formated_contacts -- list containing all contact informations
    contact_db_ids --  list containing all odoo ids related to the fetched contacts
    Returns:
    internal_contact_ids -- list of the internal ids of all updated contacts
    """
    # Step 1, upsert all contacts informations
    __upsert_contacts(formated_contacts)
    # Step 2, get the list of internal ids of all upserted
    return __get_internal_contact_ids(db, contact_db_ids)

def get_contacts_for_account_id(account_id: int, limit: int, offset: int) -> tuple[list[dict], int]:
    """
    Get one page of the contacts visible for the given account, ordered by odoo id, formatted for the endpoint

    account_id -- internal id of the account from which we want to get the data
    limit -- maximum number of contacts to return
    offset -- number of contacts to skip
    Returns:
    contacts -- list of dictionaries containing contacts data
    total -- number of contacts visible for the account
    """
    with open_connection() as conn:
        cursor = conn.cursor(dictionary=True)
        cursor.execute('''
            SELECT c.*
            FROM contacts AS c
            INNER JOIN accounts_contacts AS ac ON ac.contact_id = c.id
            WHERE ac.account_id = %s
            ORDER BY c.contact_id
            LIMIT %s OFFSET %s
        ''', [account_id, limit, offset])
        contacts = cursor.fetchall()
        cursor.execute("SELECT count(*) AS total FROM accounts_contacts WHERE account_id = %s", [account_id])
        total = cursor.fetchone()["total"]
    for contact in contacts:
        contact.pop("id")
        contact["is_company"] = bool(contact["is_company"])
    return contacts, total

def get_contact_from_account_id_contact_id(account_id: int, contact_id: int):
    sql = f'''
    SELECT c.*
    FROM contacts as c
    INNER JOIN accounts_contacts as ac on ac.contact_id = c.id
    WHERE ac.account_id = {account_id}
        AND c.contact_id = {contact_id}
    '''
    with open_connection() as conn:
        cursor = conn.cursor(dictionary=True)
        cursor.execute(sql)
        contact_infos = cursor.fetchone()
    contact_infos.pop("id")
    return contact_infos


def __upsert_contacts(formated_contacts: list[dict]) -> None:
    """
    Insert all new contact and update all existing contacts in the contacts table

    formated_contacts -- list of contacts informations to store in the database
    """
    now = datetime.now()
    with open_connection() as conn:
        insert_rows(
            conn.cursor(),
            "contacts",
            ["db", "contact_id", "email", "website", "is_company", "job_title", "created_at", "updated_at"],
            [
                [contact['db'], contact['contact_id'], contact['email'], contact['website'],
                 contact['is_company'], contact['job_title'], now, now]
                for contact in formated_contacts
            ],
            update_columns=["email", "website", "job_title", "updated_at"],
        )

def __get_internal_contact_ids(db: str, contact_db_ids: list[int]) -> list[int]:
    """
    Get all internal ids from the updated contacts in the given odoo db

    db -- name of the database in odoo systems
    contact_db_ids -- list of odoo internal contact ids
    Returns:
    formated_internal_contact_ids -- list of the internal ids of all updated contacts
    """
    with open_connection() as conn:
        rows = execute_in_batches(
            conn.cursor(),
            "SELECT id FROM contacts WHERE `db` = %s AND `contact_id` IN ({ids})",
            contact_db_ids,
            [db],
        )
    return [row[0] for row in rows]
