# backend/internals/db_connection.py
# -*- coding: utf-8 -*-

"""
Database connection and cursor management classes.
"""

from __future__ import annotations

from sqlite3 import Connection, Cursor, Row, PARSE_DECLTYPES
from threading import current_thread
from typing import Any, Dict, List, Type, Union

from flask import g

from backend.base.logging import LOGGER

class KapowarrCursor(Cursor):
    """Custom cursor class with helper methods to fetch dictionaries."""
    row_factory: Union[Type[Row], None] # type: ignore

    @property
    def lastrowid(self) -> int:
        # Ensure lastrowid returns a value, defaulting to 1 if None (or handle differently if needed)
        rowid = super().lastrowid
        return rowid if rowid is not None else 1 # Or raise an error/return 0?

    def fetchonedict(self) -> Union[dict, None]:
        """Same as `fetchone` but convert the Row object to a dict."""
        r = self.fetchone()
        if r is None:
            return r
        return dict(r)

    def fetchmanydict(self, size: Union[int, None] = 1) -> List[dict]:
        """Same as `fetchmany` but convert the Row object to a dict."""
        return [dict(e) for e in self.fetchmany(size)] # type: ignore

    def fetchalldict(self) -> List[dict]:
        """Same as `fetchall` but convert the Row object to a dict."""
        return [dict(e) for e in self]

    def exists(self) -> Union[Any, None]:
        """Return the first column of the first row, or `None` if not found."""
        r = self.fetchone()
        if r is None:
            return r
        return r[0]


class DBConnectionManager(type):
    """Metaclass to manage DBConnection instances per thread."""
    instances: Dict[int, DBConnection] = {}

    def __call__(cls, *args: Any, **kwargs: Any) -> DBConnection:
        thread_id = current_thread().native_id or -1

        if (
            thread_id not in cls.instances
            or cls.instances[thread_id].closed
        ):
            # Pass file path and timeout from args or kwargs if needed
            # Assuming file path is static or passed during app setup
            cls.instances[thread_id] = super().__call__(*args, **kwargs)

        return cls.instances[thread_id]


class DBConnection(Connection, metaclass=DBConnectionManager):
    """Custom Connection class using the DBConnectionManager metaclass."""
    file = '' # Static variable for the database file path
    timeout = 10.0 # Default timeout

    def __init__(self, database_file: str, timeout: float) -> None:
        """Create a connection with a database."""
        LOGGER.debug(f'Creating connection {self} to {database_file}')
        super().__init__(
            database_file, # Use the provided database file path
            timeout=timeout,
            detect_types=PARSE_DECLTYPES
        )
        # Set PRAGMA immediately after connection
        pragma_cursor = super().cursor()
        try:
             pragma_cursor.execute("PRAGMA foreign_keys = ON;")
             pragma_cursor.execute("PRAGMA journal_mode = WAL;") # Ensure WAL mode
        finally:
             pragma_cursor.close()

        self.closed = False
        return

    def cursor( # type: ignore
        self,
        force_new: bool = False
    ) -> KapowarrCursor:
        """Get a database cursor from the connection, managed within Flask context."""
        # Check if running within a Flask request/app context
        if not hasattr(g, 'cursors'):
            # If outside Flask context (e.g., background thread without app_context),
            # return a new cursor directly without using 'g'.
            # This requires careful management by the caller.
            # Alternatively, ensure all DB access happens within an app context.
            # For now, let's assume 'g' exists for simplicity in request handling.
            # If background tasks need DB, they should use `app.app_context()`.
            # Let's refine this based on usage patterns. If 'g' isn't always present,
            # this needs adjustment.
            # Fallback for non-Flask contexts (needs review):
            # if not _app_ctx_stack.top:
            #     c = KapowarrCursor(self)
            #     c.row_factory = Row
            #     return c
            # For now, assuming 'g' should be present when get_db is called via Flask request
            g.cursors = []


        if not g.cursors or force_new:
            # Create a new cursor if none exists for this context or if forced
            c = KapowarrCursor(self)
            c.row_factory = Row
            if force_new:
                 g.cursors.append(c) # Add new cursor to the list for this context
                 return c
            else:
                 g.cursors = [c] # Replace existing cursor(s) with the new one if not forcing new
                 return c
        else:
            # Return the existing cursor for this context
            return g.cursors[0]

    def close(self) -> None:
        """Close the database connection."""
        if not self.closed:
            LOGGER.debug(f'Closing connection {self}')
            self.closed = True
            super().close()
        return

    def __repr__(self) -> str:
        thread_name = current_thread().name
        return f'<{self.__class__.__name__}; Thread: {thread_name}; ID: {id(self)}>'