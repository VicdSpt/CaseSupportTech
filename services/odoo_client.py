import ssl
import xmlrpc.client

CONTACT_MODEL = 'res.partner'
# CONTACT_FIELDS = ['website', 'email', 'is_company', 'title']
# issue with odoo V20 for the demo
CONTACT_FIELDS = ['website', 'email', 'is_company']
JOURNAL_MODEL = 'account.journal'
JOURNAL_FIELDS = ['name', 'code', 'type', 'currency_id', 'company_id', 'active']
JOURNAL_ENTRY_MODEL = 'account.move'
JOURNAL_ENTRY_FIELDS = ['name', 'ref', 'date', 'state', 'move_type', 'journal_id', 'partner_id', 'currency_id', 'amount_total', 'company_id', 'write_date']
JOURNAL_ENTRY_LINE_MODEL = 'account.move.line'
JOURNAL_ENTRY_LINE_FIELDS = ['move_id', 'account_id', 'account_code', 'name', 'partner_id', 'debit', 'credit', 'balance', 'amount_currency', 'currency_id', 'date']
# Section and note lines are only layout lines on invoices, they have no accounting impact
NON_ACCOUNTING_LINE_TYPES = ['line_section', 'line_note']
ACCOUNT_MODEL = 'account.account'

class OdooClient:
    def __init__(self, url: str, login: str, api_key: str, db: str) -> None:
        """
        Authenticates against the Odoo instance so that records can be fetched for this user.

        url -- The URL of the Odoo instance.
        login -- The login of the user to authenticate with.
        api_key -- The API key of the user to authenticate with.
        db -- The name of the ODOO database to connect to.
        """
        self.url = url
        self.login = login
        self.api_key = api_key
        self.db = db
        # Verify the server certificate and hostname: the credentials are sent on every call.
        self.context = ssl.create_default_context()
        common = xmlrpc.client.ServerProxy('{}/xmlrpc/2/common'.format(self.url), context=self.context)
        # Authenticate with the Odoo instance and store the user ID for future requests.
        self.uid = common.authenticate(db, login, api_key, {})
        if not self.uid:
            # Odoo returns False instead of raising when the credentials are wrong.
            raise PermissionError("Odoo authentication failed for the provided credentials")
        self.models = xmlrpc.client.ServerProxy('{}/xmlrpc/2/object'.format(self.url), context=self.context)

    def fetch_all_contacts(self) -> list[dict]:
        """
        Fetches all contacts visible to the user from the Odoo database.

        Returns:
        list[dict] -- A list of dictionaries containing the contact information.
        """
        contact_ids = self.models.execute_kw(self.db, self.uid, self.api_key, CONTACT_MODEL, 'search', [[]])
        return self.models.execute_kw(self.db, self.uid, self.api_key, CONTACT_MODEL, 'read', [contact_ids], {'fields': CONTACT_FIELDS})

    def fetch_all_journals(self) -> list[dict]:
        """
        Fetches all accounting journals visible to the user from the Odoo database, archived ones included
        (archived journals can still hold journal entries).

        Returns:
        list[dict] -- A list of dictionaries containing the journal information.
        """
        return self.models.execute_kw(
            self.db, self.uid, self.api_key, JOURNAL_MODEL, 'search_read', [[]],
            {'fields': JOURNAL_FIELDS, 'context': {'active_test': False}},
        )

    def fetch_journal_entries(self, after_id: int, limit: int) -> list[dict]:
        """
        Fetches one page of journal entries, ordered by id.

        after_id -- only return entries with an id greater than this one (0 for the first page)
        limit -- maximum number of entries to return
        Returns:
        list[dict] -- A list of dictionaries containing the journal entry information.
        """
        return self.models.execute_kw(
            self.db, self.uid, self.api_key, JOURNAL_ENTRY_MODEL, 'search_read', [[('id', '>', after_id)]],
            {'fields': JOURNAL_ENTRY_FIELDS, 'order': 'id asc', 'limit': limit},
        )

    def fetch_journal_entry_lines(self, move_ids: list[int], company_id: int) -> list[dict]:
        """
        Fetches all accounting lines of the provided journal entries.
        Since Odoo 18 the account codes depend on the company: the lines must be read in the context of their
        company, otherwise the account_code is empty for every company but the user's current one.

        move_ids -- odoo ids of the journal entries, all belonging to company_id
        company_id -- odoo id of the company of those journal entries
        Returns:
        list[dict] -- A list of dictionaries containing the journal entry line information.
        """
        domain = [('move_id', 'in', move_ids), ('display_type', 'not in', NON_ACCOUNTING_LINE_TYPES)]
        return self.models.execute_kw(
            self.db, self.uid, self.api_key, JOURNAL_ENTRY_LINE_MODEL, 'search_read', [domain],
            {'fields': JOURNAL_ENTRY_LINE_FIELDS, 'context': {'allowed_company_ids': [company_id]}},
        )

    def fetch_account_names(self, account_ids: list[int], company_id: int) -> dict[int, str]:
        """
        Fetches the names of the provided accounts of the chart of accounts.

        account_ids -- odoo ids of the accounts
        company_id -- odoo id of the company the accounts are used in
        Returns:
        dict[int, str] -- {odoo account id: account name}
        """
        accounts = self.models.execute_kw(
            self.db, self.uid, self.api_key, ACCOUNT_MODEL, 'read', [account_ids],
            {'fields': ['name'], 'context': {'allowed_company_ids': [company_id]}},
        )
        return {account['id']: account['name'] for account in accounts}
