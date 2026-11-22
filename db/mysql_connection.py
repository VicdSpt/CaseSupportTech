import os
from contextlib import contextmanager
from dotenv import load_dotenv
import mysql.connector as connection

# The .env file is at the root of the repository, resolved from this file so any working directory works
load_dotenv(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".env"))
def create_connection(autocommit: bool = True):
    """
    Create a new mysql connection from the attributes included in the .env file

    autocommit -- set to False to group several statements in one transaction (commit/rollback manually)
    """
    config = {
        "host": os.environ["MYSQL_HOST"],
        "port": os.environ["MYSQL_PORT"],
        "user": os.environ["MYSQL_USER"],
        "password": os.environ["MYSQL_PASSWORD"],
        "database": os.environ["MYSQL_DATABASE"],
        "autocommit": autocommit
    }
    return connection.connect(**config)

@contextmanager
def open_connection(autocommit: bool = True):
    """
    Open a mysql connection for the duration of a `with` block and always close it, even when a query fails

    autocommit -- set to False to group several statements in one transaction (commit/rollback manually)
    """
    conn = create_connection(autocommit)
    try:
        yield conn
    finally:
        conn.close()
