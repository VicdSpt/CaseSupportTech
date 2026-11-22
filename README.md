# chift-technical-case

## Table of Contents

1. [Python Dependencies](#python-dependencies)
1. [Setup the .env file](#setup-the-env-file)
1. [Setup the Database](#setup-the-database)
    1. [Setup Docker Compose](#setup-docker-compose)
    1. [Start the  database locally](#start-the-database-locally)
    1. [Apply migrations](#apply-migrations)
1. [Create your own Odoo account](#create-your-own-odoo-account)
1. [Run the API locally](#run-the-api-locally)
1. [Run the cronjob locally](#run-the-cronjob-locally)
1. [Designed Workflow](#designed-workflow)
    1. [Create your account](#create-your-account)
    1. [Update the data for the integration](#update-the-data-for-the-integration)
    1. [Query your integrations data](#query-your-integrations-data)
1. [Endpoints](#endpoints)
    1. [Pagination](#pagination)
1. [Debugging](#debugging)
1. [To go further](#to-go-further)

## Python Dependencies

This project requires Python 3.10 or newer (the code uses the `X | None` type syntax).

To install all python dependencies, you can simply run the following command:

```
pip install -r requirements.txt
```

## Setup the .env file

To be able to run the following code, you will need to fill a .env file. For the context of this case, all variables related to the docker compose have been added with their respective environment variables. So you can copy paste the content of the template if you want to use docker compose, or setup your own database locally and put the related variables in your .env file.

## Setup the Database

### Setup Docker Compose

To make the initial configuration easier, I decided to use docker compose to run the database locally. If needed, you can find [here](https://docs.docker.com/compose/install/) all the information needed to install docker-compose.

### Start the database locally

To be able to run the database, you can use the following command:

```
docker-compose up
```

This will use the mysql docker image pinned in `docker-compose.yml` (MySQL 26.10.0) and create an instance of that database locally.

### Apply migrations

This repository contains a folder including all migration related to the database that will contain all the data. To create all tables you should be able to run the following command:

```
python3 db/migrate.py
```

This script will apply all pending migration and ignore the ones that have already been applied to your database.

## Create your own Odoo account

The API syncs its data from an Odoo instance, and **no Odoo account is provided with this case: you have to create your own**. It is free and takes a few minutes:

1. Create an Odoo account, either:
    - a free trial on <https://www.odoo.com/trial> (pick the **Accounting** app; the trial gives you API access), or
    - a local Odoo Community install if you prefer (<https://www.odoo.com/documentation/>).
1. *(Optional)* Add some data to sync. Your new account is almost empty, so the API would have nothing to return. You can either:
    - **load Odoo's demo data**: activate the developer mode (*Settings*, then at the bottom of *General Settings* click *Activate the developer mode*), then in *Settings* go to the *Developer Tools* section and click *Load demo data*. Wait for Odoo to reload: you should now have contacts, invoices and journal entries.
    - **or create your own data by hand**, if you prefer: a few contacts (companies and individuals), and a few journal entries (posted and draft) in the *Accounting* app. This is just as good for testing, you only need enough data to see your changes in the API.
1. Create an API key for your user: click your avatar, then *My Profile* (or *Preferences*), then the *Account Security* tab, then *New API Key*. Copy it right away, Odoo only shows it once.
1. Note the four values the API needs to connect to your Odoo (they are the parameters of the `create_account` endpoint, see [Create your account](#create-your-account)):
    - `url`: the URL of your instance, e.g. `https://your-company.odoo.com` (no trailing slash);
    - `db`: the technical name of your Odoo account (Odoo calls it the "database"). For a `*.odoo.com` instance, it is the sub-domain, e.g. `your-company`;
    - `login`: the email you use to log in to Odoo;
    - `api_key`: the key created above.

If you work on a feature that needs several companies (see `CANDIDATE_FEATURES.md`), enable *Multi-Companies* in Odoo's *Settings* and create a second company, with its own journals and a few entries.

## Run the API locally

Once you installed all the requirements, you should be able to run the api by using this command into a terminal:

```
python3 run.py
```

From there, the api will be listening to the port 7991 to avoid using any common port that might be used in your computer.

If you go to your browser and access <http://127.0.0.1:7991/docs>, you will be able to access the swagger documentation of all defined endpoints.

## Run the cronjob locally

To be able to run the cronjob, I used the schedule library that allows us to setup a cronjob within python.

Tu be able to run the cronjob, you can run the "update_all_accounts.py" script. It will create the cronjob and run it every 5 minutes (the schedule can be adapted from this file). Each run updates all the data of every account: contacts, journals and journal entries.

To run, run the following command:

```
python3 update_all_accounts.py
```

## Designed workflow

To be able to use this repository to create an account, update its related data and fetch those data through the api, you must follow a given workflow that was designed to work for clients that would only access the api.

### Create your account

The first step will be to connect your account. This will allow us to have access to all the information we will need to fetch the data from the odoo account and to store that in our database.

To be able to do that, you must use the create_account endpoint. This endpoint will return the different parameters that you provided in the endpoint with an external_id. This is the value that you will need to access the data of this account.

### Update the data for the integration

To be able to update the data, we will first need to run the cronjob that is responsible for the update all the accounts. Once the cronjob ran, all the data must be in the database and you can start to use the api to gather the related data.

### Query your integration's data

To query your integration's data, you must use the external_id provided in the first step (if you don't have it anymore, you can just "re create it" and we'll provide you the exact same external_id).

From there you can query the endpoints that provide the contacts, journals and journal entries data (see [Endpoints](#endpoints)).

## Endpoints

All the data endpoints take the external_id of the account in their path and only return the data this account has access to in odoo. The odoo ids are used to identify the records (`contact_id`, `journal_id`, `entry_id`).

| Method | Endpoint | Description |
|---|---|---|
| GET | `/liveness` | Check that the api is running and can access the database (`503` if the database is unreachable). |
| PUT | `/create_account?url=&login=&api_key=&db=` | Create the account (or update its api_key) and return its external_id. |
| GET | `/{external_id}/contacts` | List the contacts of the account. Paginated. |
| GET | `/{external_id}/contact_by_id?contact_id=` | Get one contact by its odoo id. |
| GET | `/{external_id}/journals` | List the journals of the account, archived ones included (`active` field). Paginated. |
| GET | `/{external_id}/journal_by_id?journal_id=` | Get one journal by its odoo id. |
| GET | `/{external_id}/journal_entries?journal_id=&date_from=&date_to=` | List the journal entries (without their lines) of one journal. `journal_id` is required, `date_from` and `date_to` (`YYYY-MM-DD`) are optional. Paginated. |
| GET | `/{external_id}/journal_entry_by_id?entry_id=` | Get one journal entry by its odoo id, with its lines (account code and name, label, partner, debit, credit, balance, currency). |

Error codes:

- `400`: the external_id does not match any account.
- `404`: the journal or journal entry does not exist or is not accessible for this account.
- `422`: a parameter is missing or invalid (e.g. no `journal_id`, a wrong date format, a page size above the maximum).

The access to the journal entries follows the access to their journal: an account can see all the entries of the journals it has access to.

### Pagination

The list endpoints (`contacts`, `journals` and `journal_entries`) are paginated with the following query parameters:

- `page`: page number, starting at 1 (default: 1).
- `size`: number of items per page (default and maximum: 100).

The items are ordered by odoo id and the response contains the pagination information, so you know how many pages there are (`total / size`, rounded up):

```
{
  "journal_entries": [...],
  "page": 1,
  "size": 100,
  "total": 16
}
```

A page after the last one returns an empty list.

Once the API is running, every endpoint and its parameters are documented at <http://127.0.0.1:7991/docs>, where you can also try them out ("Try it out" button).

## Debugging

To be able to debug the code while working on it, you can use an interactive debugger by adding the following line into your code. This will allow you to add a breakpoint into your code and allow you to do some test in the code that is currently running.

```
breakpoint()
```

