from decimal import Decimal

from db.mysql_connection import create_connection
from models.accounts_journals import get_journals_from_account_id
from models.journal_entries import (
    delete_lost_journal_entries,
    get_stored_write_dates,
    replace_journal_entry_lines,
    upsert_journal_entries,
)
from models.journals import get_internal_journal_ids_by_odoo_id
from services.odoo_client import OdooClient

PAGE_SIZE = 200


class JournalEntrySync:
    """
    Full sync of the journal entries (account.move) and their lines (account.move.line) of an account.

    - All entries are fetched page by page (ordered by id).
    - Only the entries whose odoo write_date changed since the last sync are rewritten, with all their lines.
    - Each page (entries + lines) is stored in one transaction.
    - Once every page is stored, the entries that do not exist in odoo anymore are deleted.

    The journals must be synced before (see AccountUpdater): the entries reference them, and the access of an
    account to an entry is derived from its access to the entry's journal (accounts_journals).
    """

    @classmethod
    def sync_account(cls, account_id: int, db: str, odoo_client: OdooClient) -> tuple[int, int, int]:
        """
        Sync all the journal entries visible for the account

        account_id -- internal id of the account to sync
        db -- The name of the ODOO database
        odoo_client -- authenticated odoo client of the account
        Returns:
        synced -- number of journal entries returned by odoo
        changed -- number of journal entries inserted or updated (the others did not change since the last sync)
        deleted -- number of deleted journal entries
        """
        synced_move_ids = []
        changed = 0
        after_id = 0
        while True:
            entries = odoo_client.fetch_journal_entries(after_id, PAGE_SIZE)
            if not entries:
                break
            changed += cls.__store_page(db, odoo_client, entries)
            synced_move_ids.extend(entry["id"] for entry in entries)
            after_id = entries[-1]["id"]
            if len(entries) < PAGE_SIZE:
                break
        # Only reached when every page has been stored: a failed sync never deletes anything.
        deleted = cls.__delete_lost_entries(account_id, db, synced_move_ids)
        return len(synced_move_ids), changed, deleted

    @classmethod
    def __store_page(cls, db: str, odoo_client: OdooClient, entries: list[dict]) -> int:
        """
        Store the entries of the page that changed in odoo since the last sync, with their lines, in one transaction.
        Unchanged entries are skipped: rewriting them would only burn auto-increment ids and database writes.

        db -- The name of the ODOO database
        odoo_client -- authenticated odoo client of the account
        entries -- one page of journal entries returned by odoo
        Returns:
        changed -- number of entries that were inserted or updated
        """
        stored_write_dates = cls.__get_stored_write_dates(db, [entry["id"] for entry in entries])
        entries = [entry for entry in entries if stored_write_dates.get(entry["id"]) != entry["write_date"]]
        if not entries:
            return 0

        lines, account_names = cls.__fetch_lines(odoo_client, entries)

        conn = create_connection(autocommit=False)
        cursor = conn.cursor()
        try:
            journal_ids = get_internal_journal_ids_by_odoo_id(cursor, db, [entry["journal_id"][0] for entry in entries])
            missing_journals = {entry["journal_id"][0] for entry in entries} - set(journal_ids)
            if missing_journals:
                # Should not happen as the journals are synced just before, unless one was created in between.
                raise LookupError(f"journals {sorted(missing_journals)} are not synced yet")

            formated_entries = [cls.__format_entry(db, entry, journal_ids) for entry in entries]
            internal_ids = upsert_journal_entries(cursor, formated_entries)
            formated_lines = [cls.__format_line(line, internal_ids, account_names) for line in lines]
            replace_journal_entry_lines(cursor, list(internal_ids.values()), formated_lines)
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()
        return len(entries)

    def __fetch_lines(odoo_client: OdooClient, entries: list[dict]) -> tuple[list[dict], dict[int, str]]:
        """
        Fetch the lines of the provided entries and the names of their accounts, company by company
        (since Odoo 18 the account codes depend on the company the lines are read in).

        odoo_client -- authenticated odoo client of the account
        entries -- journal entries returned by odoo
        Returns:
        lines -- all the lines of the provided entries
        account_names -- {odoo account id: account name}
        """
        move_ids_by_company = {}
        for entry in entries:
            move_ids_by_company.setdefault(entry["company_id"][0], []).append(entry["id"])
        lines = []
        account_names = {}
        for company_id, move_ids in move_ids_by_company.items():
            company_lines = odoo_client.fetch_journal_entry_lines(move_ids, company_id)
            account_ids = list({line["account_id"][0] for line in company_lines if line["account_id"]})
            if account_ids:
                account_names.update(odoo_client.fetch_account_names(account_ids, company_id))
            lines.extend(company_lines)
        return lines, account_names

    def __get_stored_write_dates(db: str, move_ids: list[int]) -> dict[int, str]:
        conn = create_connection()
        try:
            return get_stored_write_dates(conn.cursor(), db, move_ids)
        finally:
            conn.close()

    def __delete_lost_entries(account_id: int, db: str, existing_move_ids: list[int]) -> int:
        """
        Delete the stored entries of the account's journals that were not returned by odoo

        account_id -- internal id of the synced account
        db -- The name of the ODOO database
        existing_move_ids -- odoo ids of all journal entries returned by odoo during this sync
        Returns:
        deleted -- number of deleted journal entries
        """
        journal_ids = get_journals_from_account_id(account_id)
        conn = create_connection(autocommit=False)
        cursor = conn.cursor()
        try:
            deleted = delete_lost_journal_entries(cursor, db, journal_ids, existing_move_ids)
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()
        return deleted

    def __format_entry(db: str, entry: dict, journal_ids: dict[int, int]) -> dict:
        """
        Format a journal entry returned by odoo into the values to insert into the database.
        Odoo returns False for empty fields and [id, display_name] for many2one fields.
        """
        return {
            "db": db,
            "move_id": entry["id"],
            "journal_id": journal_ids[entry["journal_id"][0]],
            # draft entries have no number yet
            "name": entry["name"] or None,
            "ref": entry["ref"] or None,
            "date": entry["date"],
            "state": entry["state"],
            "move_type": entry["move_type"],
            "partner_odoo_id": entry["partner_id"][0] if entry["partner_id"] else None,
            "currency": entry["currency_id"][1] if entry["currency_id"] else None,
            # amounts are floats in odoo's API: go through str to store the exact decimal value
            "amount_total": Decimal(str(entry["amount_total"])),
            "odoo_write_date": entry["write_date"],
        }

    def __format_line(line: dict, internal_ids: dict[int, int], account_names: dict[int, str]) -> dict:
        """
        Format a journal entry line returned by odoo into the values to insert into the database.
        """
        return {
            "journal_entry_id": internal_ids[line["move_id"][0]],
            "line_id": line["id"],
            "account_code": line["account_code"] or None,
            "account_name": account_names.get(line["account_id"][0]) if line["account_id"] else None,
            "label": line["name"] or None,
            "partner_odoo_id": line["partner_id"][0] if line["partner_id"] else None,
            "debit": Decimal(str(line["debit"])),
            "credit": Decimal(str(line["credit"])),
            "balance": Decimal(str(line["balance"])),
            "amount_currency": Decimal(str(line["amount_currency"])),
            "currency": line["currency_id"][1] if line["currency_id"] else None,
            "date": line["date"],
        }
