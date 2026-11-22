import os
from datetime import datetime
from mysql_connection import create_connection

# Resolved from this file so the script works from any working directory
MIGRATIONS_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "migrations")
# Any other file in the folder (.DS_Store, editor backups, notes...) is ignored instead of being run as SQL
MIGRATION_EXTENSION = ".txt"

def is_new_migration(file_name, cursor):
    """
    This method look into the schema_versions table to ensure that we only apply new migrations

    file_name -- name of the migration file being applied
    cursor -- database accessor
    """
    cursor.execute("SELECT count(*) FROM schema_versions WHERE version = %s", [file_name])
    res = cursor.fetchall()
    return res[0][0] == 0

def apply_migration_from_file_path(file_name, cursor):
    """
    Apply the migration contained in the provided file.

    A migration file must contain a single SQL statement: cursor.execute() runs one statement only.
    MySQL commits DDL statements immediately, so a migration cannot be rolled back together with its
    schema_versions row: if recording the version fails, the migration is run again on the next call.

    file_name -- name of the file containing the migration to apply
    cursor -- database accessor
    """
    with open(os.path.join(MIGRATIONS_PATH, file_name), "r") as f:
        sql = f.read()
    cursor.execute(sql)
    cursor.execute(
        "INSERT INTO schema_versions (`version`, `created_at`) VALUES (%s, %s)",
        [file_name, datetime.now()],
    )

if __name__ == "__main__":
    conn = create_connection()

    cursor = conn.cursor()
    sql = '''
        CREATE TABLE IF NOT EXISTS `schema_versions`(
            `version` VARCHAR(255) NOT NULL,
            `created_at` datetime NOT NULL,
            PRIMARY KEY (`version`)
        )
    '''
    cursor.execute(sql)

    migration_files = sorted(
        file_name for file_name in os.listdir(MIGRATIONS_PATH) if file_name.endswith(MIGRATION_EXTENSION)
    )
    for file_name in migration_files:
        if not is_new_migration(file_name, cursor):
            # The migration has already been applied, no need to apply it twice
            print(f"Skipping migration because it's already in the schema table: {file_name}")
            continue
        apply_migration_from_file_path(file_name, cursor)
        print(f"Migration applied: {file_name}")

    conn.close()
