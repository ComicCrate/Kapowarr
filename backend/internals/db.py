# backend/internals/db.py
# -*- coding: utf-8 -*-

"""
Setting up the database and handling connections/cursors.
"""

from __future__ import annotations

from os.path import dirname, exists, isdir, join
from sqlite3 import register_adapter, register_converter, ProgrammingError
from threading import current_thread
from time import time
from typing import Any, Generator, Iterable, Union

from flask import g

# Import connection and cursor classes from the new module
from .db_connection import DBConnection, KapowarrCursor, DBConnectionManager

from backend.base.definitions import (Constants, SeedingHandling,
                                      SpecialVersion, T)
from backend.base.helpers import CommaList
from backend.base.logging import LOGGER
from backend.internals.db_migration import migrate_db

# --- Database file path management ---
_db_file_location = ''

def set_db_location(
    db_folder: Union[str, None]
) -> None:
    """Setup database location. Create folder for database and set location."""
    global _db_file_location
    from backend.base.files import create_folder, folder_path
    from backend.internals.settings import about_data # Import locally if needed

    if db_folder:
        if exists(db_folder) and not isdir(db_folder):
            raise ValueError('Database location is not a folder')

    db_file_location_temp = join(
        db_folder or folder_path(*Constants.DB_FOLDER),
        Constants.DB_NAME
    )

    LOGGER.debug(f'Setting database location: {db_file_location_temp}')

    create_folder(dirname(db_file_location_temp))

    _db_file_location = db_file_location_temp
    DBConnection.file = db_file_location_temp # Set static variable if DBConnection uses it
    if about_data: # Check if about_data is already populated
        about_data['database_location'] = db_file_location_temp

    return

def get_db_location() -> str:
    """Get the configured database file location."""
    if not _db_file_location:
         # This should ideally not happen if set_db_location is called first
         raise RuntimeError("Database location not set. Call set_db_location first.")
    return _db_file_location

# --- Connection and Cursor Handling ---

def get_db(force_new: bool = False) -> KapowarrCursor:
    """
    Get a database cursor instance or create a new one if needed.
    Relies on DBConnectionManager to handle thread-local connections.
    """
    # DBConnectionManager handles getting/creating the connection for the current thread
    connection = DBConnection(database_file=get_db_location(), timeout=Constants.DB_TIMEOUT)
    # The cursor method now handles management within Flask's 'g'
    cursor = connection.cursor(force_new=force_new)
    return cursor

def commit() -> None:
    """Commit the database transaction for the current context's connection."""
    # Get the connection associated with the current context's cursor
    # Ensure this is called within a context where get_db() provides a valid cursor
    try:
        # Assuming the first cursor in g.cursors is the primary one for the context
        if hasattr(g, 'cursors') and g.cursors:
             connection = g.cursors[0].connection
             if not connection.closed: # Check if connection is still open
                  connection.commit()
        else:
             # Handle case where commit is called outside a context with a cursor
             # This might indicate an issue or require getting the thread's connection directly
             LOGGER.warning("Commit called without an active cursor in Flask 'g'. Attempting commit via thread manager.")
             thread_id = current_thread().native_id or -1
             if thread_id in DBConnectionManager.instances:
                 connection = DBConnectionManager.instances[thread_id]
                 if not connection.closed:
                     connection.commit()

    except AttributeError:
         LOGGER.warning("Commit called outside of a Flask request context or without an initialized cursor.")
         # Optionally, try to get connection via DBConnectionManager if appropriate
         thread_id = current_thread().native_id or -1
         if thread_id in DBConnectionManager.instances:
             connection = DBConnectionManager.instances[thread_id]
             if not connection.closed:
                 connection.commit()


def iter_commit(iterable: Iterable[T]) -> Generator[T, Any, Any]:
    """Commit the database after each iteration."""
    # This function's logic remains the same, relying on the refactored commit()
    commit()
    for i in iterable:
        yield i
        commit()
    return


def close_db(e: Union[None, BaseException] = None):
    """Close database cursor(s) and commit for the current Flask context."""
    # This function now focuses on closing context-specific cursors
    # The actual connection closing is handled by DBConnectionManager or teardown
    cursors_to_close = getattr(g, 'cursors', [])
    if cursors_to_close:
        # Commit before closing cursors for this context
        try:
             # Ensure commit happens on the connection associated with the context
             if cursors_to_close[0].connection and not cursors_to_close[0].connection.closed:
                 cursors_to_close[0].connection.commit()
        except Exception as commit_error:
             LOGGER.error(f"Error committing DB transaction during close_db: {commit_error}")


        for c in cursors_to_close:
            try:
                 c.close()
            except Exception as cursor_close_error:
                 LOGGER.error(f"Error closing cursor during close_db: {cursor_close_error}")
        # Clear the context-local list
        if hasattr(g, 'cursors'):
            delattr(g, 'cursors')

    # Note: We don't explicitly close the DBConnection here anymore,
    # relying on teardown or the manager. If running outside Flask requests,
    # ensure connections are managed appropriately.
    # The original logic to close the connection based on thread name might be needed elsewhere
    # if connections are created outside Flask requests and not automatically managed.


def close_all_db() -> None:
    "Close all managed database connections."
    LOGGER.debug('Closing all managed database connections')
    # Iterate through the managed instances and close them
    instances_to_close = list(DBConnectionManager.instances.items()) # Create copy to iterate
    for thread_id, instance in instances_to_close:
        if not instance.closed:
            try:
                 # Attempt to commit before closing, handle potential errors
                 instance.commit()
            except ProgrammingError as pe:
                 # Ignore errors like "cannot operate on a closed database"
                 if "closed database" not in str(pe):
                      LOGGER.error(f"Error committing DB connection for thread {thread_id} during close_all_db: {pe}")
            except Exception as e:
                 LOGGER.error(f"Unexpected error committing DB connection for thread {thread_id} during close_all_db: {e}")

            try:
                 instance.close()
                 # Remove from manager after successful close
                 if thread_id in DBConnectionManager.instances:
                    del DBConnectionManager.instances[thread_id]
            except ProgrammingError as pe:
                 # Ignore errors like "cannot operate on a closed database"
                 if "closed database" not in str(pe):
                     LOGGER.error(f"Error closing DB connection for thread {thread_id} during close_all_db: {pe}")
            except Exception as e:
                 LOGGER.error(f"Unexpected error closing DB connection for thread {thread_id} during close_all_db: {e}")

    # Clear the manager dict after attempting to close all
    DBConnectionManager.instances.clear()

    # Optional: Perform a final check/commit with a temporary connection if needed
    # try:
    #     c = DBConnection(database_file=get_db_location(), timeout=20.0)
    #     c.commit()
    #     c.close()
    # except Exception as final_close_error:
    #     LOGGER.error(f"Error during final DB check/close in close_all_db: {final_close_error}")


def setup_db() -> None:
    """
    Setup the database tables and default config when they aren't setup yet.
    """
    # Ensure Settings import doesn't cause circular dependency issues
    # May need local import if Settings depends on db implicitly
    from backend.internals.settings import Settings, task_intervals

    cursor = get_db() # Get cursor using the refactored method

    # Type Adapters/Converters (remain the same)
    register_adapter(bool, lambda b: int(b))
    register_converter("BOOL", lambda b: b == b'1')
    register_adapter(CommaList, lambda c: str(c))
    register_adapter(SeedingHandling, lambda e: e.value)
    register_adapter(SpecialVersion, lambda e: e.value)

    # Schema setup commands (remain the same)
    setup_commands = """
        CREATE TABLE IF NOT EXISTS config(
            key VARCHAR(100) PRIMARY KEY,
            value BLOB
        );
        CREATE TABLE IF NOT EXISTS root_folders(
            id INTEGER PRIMARY KEY,
            folder VARCHAR(254) UNIQUE NOT NULL
        );
        CREATE TABLE IF NOT EXISTS volumes(
            id INTEGER PRIMARY KEY,
            comicvine_id INTEGER NOT NULL,
            title VARCHAR(255) NOT NULL,
            alt_title VARCHAR(255),
            year INTEGER(5),
            publisher VARCHAR(255),
            volume_number INTEGER(8) DEFAULT 1,
            description TEXT,
            site_url TEXT NOT NULL DEFAULT "",
            cover BLOB,
            monitored BOOL NOT NULL DEFAULT 0,
            monitor_new_issues BOOL NOT NULL DEFAULT 1,
            root_folder INTEGER NOT NULL,
            folder TEXT,
            custom_folder BOOL NOT NULL DEFAULT 0,
            last_cv_fetch INTEGER(8) DEFAULT 0,
            special_version VARCHAR(255),
            special_version_locked BOOL NOT NULL DEFAULT 0,

            FOREIGN KEY (root_folder) REFERENCES root_folders(id)
                ON DELETE RESTRICT -- Consider RESTRICT or SET NULL based on desired behavior
        );
        CREATE TABLE IF NOT EXISTS issues(
            id INTEGER PRIMARY KEY,
            volume_id INTEGER NOT NULL,
            comicvine_id INTEGER NOT NULL UNIQUE,
            issue_number VARCHAR(20) NOT NULL,
            calculated_issue_number FLOAT(20) NOT NULL,
            title VARCHAR(255),
            date VARCHAR(10),
            description TEXT,
            monitored BOOL NOT NULL DEFAULT 1,

            FOREIGN KEY (volume_id) REFERENCES volumes(id)
                ON DELETE CASCADE
        );
        CREATE INDEX IF NOT EXISTS issues_volume_number_index
            ON issues(volume_id, calculated_issue_number);
        CREATE TABLE IF NOT EXISTS files(
            id INTEGER PRIMARY KEY,
            filepath TEXT UNIQUE NOT NULL,
            size INTEGER
        );
        CREATE TABLE IF NOT EXISTS issues_files(
            file_id INTEGER NOT NULL,
            issue_id INTEGER NOT NULL,

            FOREIGN KEY (file_id) REFERENCES files(id)
                ON DELETE CASCADE,
            FOREIGN KEY (issue_id) REFERENCES issues(id)
                ON DELETE CASCADE, -- Cascade delete here too? Review implications
            CONSTRAINT PK_issues_files PRIMARY KEY (
                file_id,
                issue_id
            )
        );
        CREATE TABLE IF NOT EXISTS volume_files(
            file_id INTEGER PRIMARY KEY,
            volume_id INTEGER NOT NULL,
            file_type VARCHAR(15) NOT NULL,

            FOREIGN KEY (volume_id) REFERENCES volumes(id)
                ON DELETE CASCADE,
            FOREIGN KEY (file_id) REFERENCES files(id)
                ON DELETE CASCADE
        );
        CREATE TABLE IF NOT EXISTS external_download_clients(
            id INTEGER PRIMARY KEY,
            download_type INTEGER NOT NULL,
            client_type VARCHAR(255) NOT NULL,
            title VARCHAR(255) NOT NULL,
            base_url TEXT NOT NULL,
            username VARCHAR(255),
            password VARCHAR(255),
            api_token VARCHAR(255)
        );
        CREATE TABLE IF NOT EXISTS download_queue(
            id INTEGER PRIMARY KEY,
            volume_id INTEGER NOT NULL,
            client_type VARCHAR(255) NOT NULL,
            external_client_id INTEGER,

            download_link TEXT NOT NULL,
            covered_issues VARCHAR(255),
            force_original_name BOOL,

            source_type VARCHAR(25) NOT NULL,
            source_name VARCHAR(255) NOT NULL,

            web_link TEXT,
            web_title TEXT,
            web_sub_title TEXT,

            FOREIGN KEY (external_client_id) REFERENCES external_download_clients(id)
                 ON DELETE SET NULL, -- Keep queue item if client is deleted? Or Cascade?
            FOREIGN KEY (volume_id) REFERENCES volumes(id)
                 ON DELETE CASCADE -- Delete queue item if volume is deleted
        );
        CREATE TABLE IF NOT EXISTS download_history(
            web_link TEXT,
            web_title TEXT,
            web_sub_title TEXT,
            file_title TEXT,

            volume_id INTEGER,
            issue_id INTEGER,

            source VARCHAR(25),
            downloaded_at INTEGER NOT NULL CHECK (downloaded_at > 0),

            FOREIGN KEY (volume_id) REFERENCES volumes(id)
                ON DELETE SET NULL,
            FOREIGN KEY (issue_id) REFERENCES issues(id)
                ON DELETE SET NULL
        );
        CREATE TABLE IF NOT EXISTS task_history(
            task_name NOT NULL,
            display_title NOT NULL,
            run_at INTEGER NOT NULL
        );
        CREATE TABLE IF NOT EXISTS task_intervals(
            task_name PRIMARY KEY,
            interval INTEGER NOT NULL,
            next_run INTEGER NOT NULL
        );
        CREATE TABLE IF NOT EXISTS blocklist(
            id INTEGER PRIMARY KEY,
            volume_id INTEGER,
            issue_id INTEGER,

            web_link TEXT,
            web_title TEXT,
            web_sub_title TEXT,

            download_link TEXT UNIQUE,
            source VARCHAR(30),

            reason INTEGER NOT NULL CHECK (reason > 0),
            added_at INTEGER NOT NULL CHECK (added_at > 0),

            FOREIGN KEY (volume_id) REFERENCES volumes(id)
                ON DELETE SET NULL,
            FOREIGN KEY (issue_id) REFERENCES issues(id)
                ON DELETE SET NULL
        );
        CREATE TABLE IF NOT EXISTS credentials(
            id INTEGER PRIMARY KEY,
            source VARCHAR(30) NOT NULL,
            username TEXT,
            email TEXT,
            password TEXT,
            api_key TEXT
        );
    """
    cursor.executescript(setup_commands)
    commit() # Commit schema changes

    # Initialize settings (which might insert defaults)
    # Ensure Settings() call doesn't run into DB issues if called during schema setup
    # It might be safer to call this *after* executescript
    settings = Settings()
    # settings_values = settings.get_settings() # This calls _fetch_settings

    # Set log level (assuming set_log_level doesn't need DB)
    # Local import to avoid potential circular dependency if logging uses settings
    from backend.base.logging import set_log_level
    set_log_level(settings.sv.log_level)

    # Run migrations
    migrate_db()
    commit() # Commit migration changes

    # DB Migration might change settings, so update cache just to be sure.
    settings._fetch_settings()

    # Generate api key if needed
    if not settings.sv.api_key:
        settings.generate_api_key() # This commits internally

    # Add/Update task intervals
    LOGGER.debug(f'Inserting/Updating task intervals: {task_intervals}')
    current_time = round(time())
    cursor.executemany(
        """
        INSERT INTO task_intervals(task_name, interval, next_run)
        VALUES (?, ?, ?)
        ON CONFLICT(task_name) DO
        UPDATE SET interval = excluded.interval;
        """,
        ((k, v, current_time) for k, v in task_intervals.items())
    )
    commit() # Commit task interval changes

    return