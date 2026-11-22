from services.odoo_client import OdooClient
import uuid
from datetime import datetime
from db.mysql_connection import open_connection

def upsert_account(url: str, login: str, api_key: str, db: str) -> str:
    """
    Insert the provided values as an account in the accounts table.
    If the provided account already exist, update the credentials and return the existing external id.

    url -- The URL of the Odoo instance.
    login -- The login of the user to authenticate with.
    api_key -- The API key of the user to authenticate with.
    db -- The name of the ODOO database to connect to.

    Returns:
    external_id -- the external id of the account provided
    """
    try:
        OdooClient(url, login, api_key, db)
    except:
        raise AttributeError("The parameter combination is wrong")
    __upsert_account(url, login, api_key, db, uuid.uuid4())

    return get_external_id_from_db_login(db, login)

def get_external_id_from_db_login(db: str, login: str) -> str:
    """
    Get the external id of the account with the provided db and login

    db -- The name of the ODOO database to connect to.
    login -- The login of the user to authenticate with.
    Returns:
    external_id -- the external id of the account provided
    """
    sql = f'''
        SELECT external_id
        FROM accounts
        WHERE db = '{db}' AND login = '{login}'
    '''
    with open_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(sql)
        res = cursor.fetchone()
    return res[0]

def get_account_from_id(id: int) -> dict:
    """
    Get all the account attributes from the provided account id

    id -- id of the account in the database
    Returns:
    account -- Dictionary containing all the account informations
    """
    sql = f'''
        SELECT *
        FROM accounts
        WHERE id = {id}
    '''
    with open_connection() as conn:
        cursor = conn.cursor(dictionary=True)
        cursor.execute(sql)
        return cursor.fetchone()

def get_account_from_external_id(external_id: str) -> int:
    """
    Get the account id from the provided external id

    external_id -- uuid of the account in the database
    Returns:
    account_id -- Dictionary containing all the account informations
    """
    # external_id comes straight from the URL, so it must be passed as a query parameter
    # to avoid SQL injection (e.g. "x' OR '1'='1" would match any account).
    sql = '''
        SELECT id
        FROM accounts
        WHERE `external_id` = %s
    '''
    with open_connection() as conn:
        cursor = conn.cursor(dictionary=True)
        cursor.execute(sql, [external_id])
        rows = cursor.fetchone()
    if rows is None:
        raise AttributeError("The external id do not exist")
    return rows['id']

def get_all_account_ids() -> list[int]:
    """
    Get the id of all accounts in the accounts table

    Returns:
    account_ids -- list containing the internal ids of all accounts
    """
    sql = f'''
        SELECT id
        FROM accounts
    '''
    with open_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(sql)
        query_result = cursor.fetchall()
    all_account_ids = []
    for row in query_result:
        all_account_ids.append(row[0])
    return all_account_ids

def __upsert_account(url: str, login: str, api_key: str, db: str, external_id: int) -> None:
    """
    Perform the upsert operation for the provided parameters into the accounts table

    url -- The URL of the Odoo instance.
    login -- The login of the user to authenticate with.
    api_key -- The API key of the user to authenticate with.
    db -- The name of the ODOO database to connect to.
    external_id -- generated external id of the account
    """
    now = datetime.now()
    sql = f'''
        INSERT INTO accounts (`db`, `login`, `url`, `credentials`, `external_id`, `created_at`, `updated_at`)
        VALUES ('{db}', '{login}', '{url}', '{api_key}', '{external_id}', '{now}', '{now}')
        ON DUPLICATE KEY UPDATE
            `credentials` = VALUES(`credentials`),
            `updated_at` = VALUES(`updated_at`);
    '''
    with open_connection() as conn:
        conn.cursor().execute(sql)