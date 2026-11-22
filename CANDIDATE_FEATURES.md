# Feature requests for candidates

> **How to work on this case:** please work with **git**, in a repository on **GitHub** (commit as you go, so we can follow your progress). **Please send us the link to your GitHub repository the day before our meeting.**

You receive this codebase: an API that syncs data (contacts, journals, journal entries) from Odoo accounts into a MySQL database and exposes it to clients. Read the `README.md` to set it up. No Odoo account is provided: you create your own Odoo account (see "Create your own Odoo account" in the `README.md`) and fill it with some data to test your work.

Choose as many of the features listed below as you like and implement them in the existing codebase. Any additional optimizations are also welcome.

What to hand in:

- your code, in your GitHub repository, with any new migration in `db/migrations`;
- example requests for your new endpoints (curl commands, a Postman collection, or similar);
- a short note (half a page is enough) that explains:
  - what you built and the choices you made;
  - what you would do with more time;
  - any bug or risk you noticed in the existing code, and how you would prioritise it.

---

## Feature 1: sync status endpoint

### Context

Clients regularly contact support with messages like:

> I just connected my Odoo account and `/contacts` returns nothing. Did the connection fail?

> Nothing I change in Odoo shows up in your API since yesterday.

Today a client can't tell whether their data has been synced yet, when it was last synced, or whether the last sync failed. Sync errors are only printed in the cron's output.

### What to build

A new endpoint `GET /{external_id}/status` that tells a client the state of their data.

### Requirements

- It returns at least:
  - when the last sync started and finished;
  - whether it succeeded, failed, or is still running;
  - the error message when it failed, without leaking credentials or internal details;
  - the number of synced records per object (contacts, journals, journal entries);
  - the date of the last **successful** sync.
- An account that has never been synced has a clear state (for example `never_synced`), not an error.
- An unknown `external_id` behaves like on the other endpoints.
- Sync status must be kept in the database, not in memory: the API and the cron are separate processes.

### Example response

```json
{
  "status": "failed",
  "last_sync_started_at": "2026-11-02T16:05:00",
  "last_sync_finished_at": "2026-11-02T16:05:12",
  "last_successful_sync_at": "2026-11-02T16:00:41",
  "error": "Odoo authentication failed for the provided credentials",
  "counts": { "contacts": 410, "journals": 37, "journal_entries": 2704 }
}
```

The exact format is up to you, as long as you explain it.

### Things to think about

- Where in `services/account_updater.py` a sync can fail, and whether a failure in one step (for example contacts) should hide what happened in the others.
- Whether you keep only the last run or a history of runs.

---

## Feature 2: sync a new Odoo object

### Context

Clients want more accounting data than contacts, journals and journal entries. Add **one** of the following (or another object agreed with your interviewer):

- **Invoices with their payment status:** customer and vendor invoices and credit notes (`account.move` where `move_type` is an invoice type), with the payment state (`payment_state`), the amount still due (`amount_residual`) and the due date (`invoice_date_due`).
- **Chart of accounts:** the accounts (`account.account`) with their code, name and type.

### What to build

The full flow, the same way the existing objects work:

1. fetch the data from Odoo (`services/odoo_client.py`);
2. format it (`services/account_updater.py` or a dedicated service);
3. store it with a migration and an upsert (`models/`);
4. delete what no longer exists in Odoo;
5. expose it with a paginated list endpoint and a get-by-id endpoint, scoped to what the account can access.

### Requirements

- Follow the existing structure and conventions unless you have a reason not to, and explain it.
- The endpoints only return data the account has access to.
- Amounts must keep their exact value.
- A sync that fails halfway must not leave partial or deleted data.

### Things to think about

- How Odoo returns empty values (`False`) and relational fields (`[id, "name"]`).
- Odoo can hold **several companies** in one account. Enable multi-company in your own Odoo account and check what that means for your object (codes, names, currencies).
- Archived records in Odoo: should they be synced, and how would a client know?
- Can your new object reuse what is already synced (for example invoices are journal entries)?

---

## Feature 3: filters on the list endpoints

### Context

Clients pull our data into their own tools. Today they must download every page of a list and filter on their side. Typical requests:

> I only want the posted entries, not the drafts.

> I want to fetch only what changed since my last call, instead of everything every time.

> I'm looking for the contact with this email.

### What to build

Add query parameters to the existing list endpoints:

- `GET /{external_id}/journal_entries`:
  - `state` (for example `posted`, `draft`, `cancel`);
  - `partner_id` (Odoo id of the partner);
  - `updated_since` (datetime): entries changed since this moment.
- `GET /{external_id}/contacts`:
  - `email` (exact match);
  - `is_company` (`true`/`false`);
  - `updated_since` (datetime).

### Requirements

- Filters are optional and can be combined. Without a filter, the endpoints behave exactly as today.
- `total` in the response reflects the filters, so pagination keeps working.
- Invalid values return a `422` with a clear message (for example an unknown `state`, or a badly formatted date).
- Queries must stay parameterized (no user input concatenated into SQL).
- Document the new parameters in the `README.md` and in the Swagger docs (`/docs`).

### Things to think about

- `updated_since` is the feature clients will rely on to sync incrementally. Which date should it use: our `updated_at`, or Odoo's `odoo_write_date`? What happens to records deleted since the client's last call?
- Which indexes the new filters need if an account has hundreds of thousands of entries.
