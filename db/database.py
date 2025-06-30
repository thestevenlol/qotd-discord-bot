import sqlite3
import os

from constants import sqlite_db_path

connection = None
DATABASE_FILE_PATH = sqlite_db_path + "/data.db"


def validate_db_path() -> bool:
    if not os.path.exists(sqlite_db_path):
        os.makedirs(os.path.dirname(sqlite_db_path), exist_ok=True)
        return True

    return False


def get_connection() -> sqlite3.Connection:
    global connection

    print(os.path.abspath(DATABASE_FILE_PATH))

    # First, validate paths.
    paths_created = validate_db_path()

    if paths_created:
        print("Database path created.")

    if not paths_created:
        print("Database path OK.")

    # Next, check if a connection exists. If yes, return.
    if connection is None:
        connection = sqlite3.connect(DATABASE_FILE_PATH)

    # if a connection is not None (i.e. exists), check if it is actually an sqlite3 Connection object
    if connection is not sqlite3.Connection:
        connection = sqlite3.connect(DATABASE_FILE_PATH)

    return connection

def create_tables():
    pass