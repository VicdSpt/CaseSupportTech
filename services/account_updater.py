from datetime import datetime

from models.accounts import get_account_from_id, get_all_account_ids, set_last_sync_started, set_success_update, set_fail_update
from models.accounts_contacts import (
    delete_lost_contacts_for_accounts,
    upsert_accounts_contacts_connections,
)
from models.contacts import upsert_contacts
from models.accounts_journals import (
    delete_lost_journals_for_account,
    upsert_accounts_journals_connections,
)
from models.journals import upsert_journals
from services.journal_entry_sync import JournalEntrySync
from services.odoo_client import OdooClient

import xmlrpc.client

# TECH CASE
# traduit une erreur de sync en message court et sûr pour le client (sans détails internes)

def get_safe_error_message(e: Exception) -> str:
    if isinstance(e, PermissionError):
        return "Odoo authentication failed for the provided credentials"
    elif isinstance(e, xmlrpc.client.Fault):
        return "Odoo rejected the request. Please contact support."
    elif isinstance(e, OSError):
        return "Could not reach the Odoo instance. Please check the URL."
    else:
        return "An internal error occurred during the sync. Our team has been notified."


class AccountUpdater:
    @classmethod
    def update_all_accounts(cls):
        """
        Get the list of all accounts existing in the database and update every single one of them
        """
        # Step 1: Get all account ids,
        account_ids = get_all_account_ids()
        # Step 2: Update each accounts 1 by 1
        for id in account_ids:
            try:
                cls.update_account(id)
            except Exception as e:
                # One broken account must not prevent the others from being updated.
                print(f"account with id={id} could not be updated: {e!r}")

                # CASE - une étape a échoué : on enregistre l'échec avec le message d'erreur
                set_fail_update(id, error_message=get_safe_error_message(e))

        print("all accounts have been udpated")

    @classmethod
    def update_account(cls, id: int):
        """
        Update a specific account by fetching it's contacts

        id -- internal id of the account to update
        """
        # Step 1: Fetch the data using the odoo client
        account = get_account_from_id(id) 

        if account is None:
            # We asked to update an account that do not exist, so we cannot do anything
            print(f"The provided account with id={id} do not exist. Cannot update anything.")
            return None
        
        # CASE
        set_last_sync_started(id)
        
        odoo_client = OdooClient(account["url"], account["login"], account["credentials"], account["db"])
        contact_infos = odoo_client.fetch_all_contacts()
        # Step 2: Format the data if needed
        formated_contacts, contact_db_ids = cls.__format_contacts(account["db"], contact_infos)
        # Step 3 insert the data in the database
        # Step 3.1: upsert the contacts in the database to get their internal ids
        upserted_internal_ids = upsert_contacts(account["db"], formated_contacts, contact_db_ids)
        # Step 3.2: delete link with lost contacts. accounts_contacts references contacts.id,
        # so it must be compared against internal ids, not odoo ids.
        delete_lost_contacts_for_accounts(id, upserted_internal_ids)
        # Step 3.3: insert the relation between the account and the upserted contacts
        upsert_accounts_contacts_connections(id, upserted_internal_ids)
        # Step 4: fetch the journals and store them the same way as the contacts
        journal_infos = odoo_client.fetch_all_journals()
        formated_journals, journal_db_ids = cls.__format_journals(account["db"], journal_infos)
        # Step 4.1: upsert the journals in the database to get their internal ids
        upserted_journal_ids = upsert_journals(account["db"], formated_journals, journal_db_ids)
        # Step 4.2: delete link with journals the account cannot see anymore
        delete_lost_journals_for_account(id, upserted_journal_ids)
        # Step 4.3: insert the relation between the account and the upserted journals
        upsert_accounts_journals_connections(id, upserted_journal_ids)
        # Step 5: sync the journal entries (needs the journals of step 4)
        synced_entries, changed_entries, deleted_entries = JournalEntrySync.sync_account(id, account["db"], odoo_client)

        # CASE - toutes les étapes ont réussi : on enregistre le succès
        set_success_update(id)

        print(f"account with id={id} properly updated ({synced_entries} journal entries in odoo, "
              f"{changed_entries} inserted or updated, {deleted_entries} deleted)")

    def __format_journals(db: str, journal_infos: list[dict]) -> tuple[list[dict], list[int]]:
        """
        Format the provided journals to have a dictionary with the values to insert into the database

        db -- The name of the ODOO database to connect to.
        journal_infos -- the list of all journals returned by odoo's system
        Returns:
        formated_journals -- the list containing all journals with the proper formated dictionary
        journal_db_ids -- the list of all odoo ids matching the detected journals
        """
        formated_journals = []
        journal_db_ids = []
        for infos in journal_infos:
            journal_db_ids.append(infos["id"])
            formated_journals.append({
                "db": db,
                "journal_id": infos["id"],
                "name": infos["name"],
                "code": infos["code"],
                "type": infos["type"],
                # currency_id is a many2one field: Odoo returns [id, display_name], or False when
                # the journal uses the company currency
                "currency": infos["currency_id"][1] if infos["currency_id"] else None,
                "company": infos["company_id"][1] if infos["company_id"] else None,
                "active": infos["active"],
            })
        return formated_journals, journal_db_ids

    def __format_contacts(db: str, contact_infos: list[dict]) -> list[list[dict], list[int]]:
        """
        Format the provided contact to have a hash with the values to insert into the database

        db -- The name of the ODOO database to connect to.
        contact_infos -- the list of all contacts returned by odoo's system
        Returns:
        formated_contacts -- the list containing all contacts with the proper formated disctionary
        contact_db_ids -- the list of all odoo ids matching the detected contacts
        """
        formated_contacts = []
        contact_db_ids = []
        for infos in contact_infos:
            formated_contact = {
                "db": db,
                "contact_id": infos["id"],
                "email": infos["email"] if infos["email"] is not False else None,
                "website": infos["website"] if infos["website"] is not False else None,
                "is_company": infos["is_company"],
                # title is a many2one field: Odoo returns it as [id, display_name]
                # "job_title": infos["title"][1] if infos["title"] else None,
                # issue with odoo v20 for the demo
                "job_title": infos["function"] if infos["function"] is not False else None,
                "created_at": datetime.now(),
                "updated_at": datetime.now()
            }
            contact_db_ids.append(infos["id"])
            formated_contacts.append(formated_contact)
        return formated_contacts, contact_db_ids

