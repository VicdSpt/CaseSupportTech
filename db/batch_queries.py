"""
Helpers for the queries shared by the models. The lists synced from odoo can be long, so the IN lists and the
multi-row INSERTs are split in batches to keep every query a reasonable size.
All values are passed as query parameters so the driver escapes them (quotes, NULLs, injection).
"""

BATCH_SIZE = 100

def batches(items: list, size: int = BATCH_SIZE):
    """
    Yield the provided list in consecutive slices of at most `size` items
    """
    for start in range(0, len(items), size):
        yield items[start:start + size]

def placeholders(count: int) -> str:
    """
    Return `count` comma separated query placeholders, e.g. "%s, %s, %s"
    """
    return ", ".join(["%s"] * count)

def execute_in_batches(cursor, sql: str, ids: list, params: list | tuple = ()) -> list:
    """
    Run the query once per batch of ids and return all the fetched rows (none for a DELETE).
    Nothing is run when ids is empty, as `IN ()` is not valid SQL.

    cursor -- database cursor to use
    sql -- query with `{ids}` where the IN list goes, e.g. "DELETE FROM journals WHERE `id` IN ({ids})"
    ids -- values of the IN list
    params -- values of the placeholders that come before the IN list
    Returns:
    rows -- the rows returned by all the batches
    """
    rows = []
    for batch in batches(ids):
        cursor.execute(sql.format(ids=placeholders(len(batch))), [*params, *batch])
        if cursor.with_rows:
            rows.extend(cursor.fetchall())
    return rows

def insert_rows(cursor, table: str, columns: list[str], rows: list[list], update_columns: list[str] = ()) -> None:
    """
    Insert the rows in batches. With update_columns, a row that already exists (same unique key) has those columns
    updated instead (ON DUPLICATE KEY UPDATE).

    cursor -- database cursor to use
    table -- name of the table
    columns -- names of the inserted columns
    rows -- values to insert, one list per row, in the order of columns
    update_columns -- columns to update when the row already exists
    """
    column_names = ", ".join(f"`{column}`" for column in columns)
    row_placeholders = f"({placeholders(len(columns))})"
    on_duplicate_key = ""
    if update_columns:
        on_duplicate_key = " ON DUPLICATE KEY UPDATE " + ", ".join(
            f"`{column}` = VALUES(`{column}`)" for column in update_columns
        )
    for batch in batches(rows):
        values = ", ".join([row_placeholders] * len(batch))
        cursor.execute(
            f"INSERT INTO `{table}` ({column_names}) VALUES {values}{on_duplicate_key}",
            [value for row in batch for value in row],
        )
