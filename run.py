from datetime import date

import uvicorn
from fastapi import Depends, FastAPI, HTTPException, Query
from models.accounts import upsert_account, get_account_from_external_id, get_account_from_id, get_counts_for_account_id
from db.mysql_connection import create_connection
from models.contacts import (
    get_contacts_for_account_id,
    get_contact_from_account_id_contact_id,
)
from models.journals import (
    get_journals_for_account_id,
    get_journal_from_account_id_journal_id,
)
from models.journal_entries import (
    get_journal_entries_for_account_id,
    get_journal_entry_from_account_id_move_id,
)

app = FastAPI()

MAX_PAGE_SIZE = 100


class Pagination:
    """
    Pagination parameters shared by all the list endpoints.
    """

    def __init__(
        self,
        page: int = Query(1, ge=1, description="Page number, starting at 1"),
        size: int = Query(
            MAX_PAGE_SIZE,
            ge=1,
            le=MAX_PAGE_SIZE,
            description=f"Number of items per page (default and max {MAX_PAGE_SIZE})",
        ),
    ):
        self.page = page
        self.size = size
        self.offset = (page - 1) * size

    def response(self, key: str, items: list, total: int) -> dict:
        return {
            key: items,
            "page": self.page,
            "size": self.size,
            "total": total,
        }


@app.get(
    "/liveness",
    responses={
        503: {"description": "The connection to the database could not be established"}
    },
)
def liveness():
    """
    Check if the api is properly setup and if the database can properly be accessed.
    """
    try:
        create_connection().close()
    except:
        raise HTTPException(
            status_code=503,
            detail="The connection to the database could not be established",
        )


@app.put(
    "/create_account",
    responses={400: {"description": "Parameter combination is not working."}},
)
def create_account(url: str, login: str, api_key: str, db: str) -> dict:
    """
    Ensure that the provided arguments can access ODOO's data then create an account with the related information.
    If the account already exist, then update the api_key.
    """
    try:
        external_id = upsert_account(url, login, api_key, db)
    except AttributeError:
        raise HTTPException(
            status_code=400, detail="Parameter combination is not working"
        )
    return {
        "external_id": external_id,
        "url": url,
        "login": login,
        "db": db,
        "api_key": api_key,
    }


@app.get(
    "/{external_id}/contacts",
    responses={400: {"description": "The provided account do not exist."}},
)
def get_all_contacts_for_external_id(
    external_id: str, pagination: Pagination = Depends()
):
    """
    Get one page of the contacts that are accessible for the provided external id, ordered by odoo id.
    """
    try:
        account_id = get_account_from_external_id(external_id)
    except AttributeError:
        raise HTTPException(status_code=400, detail="The provided account do not exist")
    contacts, total = get_contacts_for_account_id(
        account_id, pagination.size, pagination.offset
    )
    return pagination.response("contacts", contacts, total)


@app.get(
    "/{external_id}/contact_by_id",
    responses={400: {"description": "The provided account do not exist."}},
)
def get_contact_by_contact_id(external_id: str, contact_id: int):
    """
    Get the data for the odoo contact id provided in the endpoint.
    """
    try:
        account_id = get_account_from_external_id(external_id)
        contact = get_contact_from_account_id_contact_id(account_id, contact_id)
    except AttributeError:
        raise HTTPException(status_code=400, detail="The provided account do not exist")
    return {"contact": contact}


@app.get(
    "/{external_id}/journals",
    responses={400: {"description": "The provided account do not exist."}},
)
def get_all_journals_for_external_id(
    external_id: str, pagination: Pagination = Depends()
):
    """
    Get one page of the journals that are accessible for the provided external id, ordered by odoo id.
    """
    try:
        account_id = get_account_from_external_id(external_id)
    except AttributeError:
        raise HTTPException(status_code=400, detail="The provided account do not exist")
    journals, total = get_journals_for_account_id(
        account_id, pagination.size, pagination.offset
    )
    return pagination.response("journals", journals, total)


@app.get(
    "/{external_id}/journal_by_id",
    responses={
        400: {"description": "The provided account do not exist."},
        404: {
            "description": "The journal do not exist or is not accessible for this account."
        },
    },
)
def get_journal_by_journal_id(external_id: str, journal_id: int):
    """
    Get the data for the odoo journal id provided in the endpoint.
    """
    try:
        account_id = get_account_from_external_id(external_id)
    except AttributeError:
        raise HTTPException(status_code=400, detail="The provided account do not exist")
    journal = get_journal_from_account_id_journal_id(account_id, journal_id)
    if journal is None:
        raise HTTPException(
            status_code=404,
            detail="The journal do not exist or is not accessible for this account",
        )
    return {"journal": journal}


@app.get(
    "/{external_id}/journal_entries",
    responses={
        400: {"description": "The provided account do not exist."},
        404: {
            "description": "The journal do not exist or is not accessible for this account."
        },
    },
)
def get_all_journal_entries_for_external_id(
    external_id: str,
    journal_id: int = Query(
        ..., description="Odoo id of the journal whose entries are returned"
    ),
    date_from: date | None = Query(
        None, description="Only return the entries dated on or after this date"
    ),
    date_to: date | None = Query(
        None, description="Only return the entries dated on or before this date"
    ),
    pagination: Pagination = Depends(),
):
    """
    Get one page of the journal entries (without their lines) of the provided journal, ordered by odoo id.
    The journal must be accessible for the provided external id.
    """
    try:
        account_id = get_account_from_external_id(external_id)
    except AttributeError:
        raise HTTPException(status_code=400, detail="The provided account do not exist")
    if get_journal_from_account_id_journal_id(account_id, journal_id) is None:
        raise HTTPException(
            status_code=404,
            detail="The journal do not exist or is not accessible for this account",
        )
    journal_entries, total = get_journal_entries_for_account_id(
        account_id, pagination.size, pagination.offset, journal_id, date_from, date_to
    )
    return pagination.response("journal_entries", journal_entries, total)


@app.get(
    "/{external_id}/journal_entry_by_id",
    responses={
        400: {"description": "The provided account do not exist."},
        404: {
            "description": "The journal entry do not exist or is not accessible for this account."
        },
    },
)
def get_journal_entry_by_entry_id(external_id: str, entry_id: int):
    """
    Get the data and the lines of the odoo journal entry id provided in the endpoint.
    """
    try:
        account_id = get_account_from_external_id(external_id)
    except AttributeError:
        raise HTTPException(status_code=400, detail="The provided account do not exist")
    journal_entry = get_journal_entry_from_account_id_move_id(account_id, entry_id)
    if journal_entry is None:
        raise HTTPException(
            status_code=404,
            detail="The journal entry do not exist or is not accessible for this account",
        )
    return {"journal_entry": journal_entry}

# TECH CASE permet de vérifier l'état des data d'une synchronisation (statut, dates, erreur, counts)
@app.get(
    "/{external_id}/status",
    responses={400: {"description": "The provided account do not exist."}},
)
def get_sync_status(external_id: str):
    """
    Get the data from the sync status endpoint
    """
    try:
        account_id = get_account_from_external_id(external_id)
    except AttributeError:
        raise HTTPException(status_code=400, detail="The provided account do not exist")
    account = get_account_from_id(account_id)
    counts = get_counts_for_account_id(account_id)
    if account["last_sync_started_at"] is None:
        status = "never_synced"
    else:
        status = account["last_sync_status"]
    return {
        "status": status,
        "last_sync_started_at": account["last_sync_started_at"],
        "last_sync_finished_at": account["last_sync_finished_at"],
        "last_successful_sync_at": account["last_sync_successful_at"],
        "error": account["last_sync_error"],
        "counts": counts,
    }


if __name__ == "__main__":
    uvicorn.run(app, host="127.0.0.1", port=7991)
