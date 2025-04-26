# -*- coding: utf-8 -*-

"""
Functions related to task history.
"""

from typing import List, Dict
from backend.internals.db import get_db
from backend.base.logging import LOGGER
# Import task_library from handler (circular import if handler imports this, handle carefully)
# One way is to pass task_library to get_task_planning if needed, or define task titles elsewhere
# For now, assuming task_library is accessible, possibly via importing the handler module itself
# Be mindful of potential circular dependencies
# Alternative: Define task titles in definitions.py or a central config
# from .handler import task_library # Example - Check for circular imports

def get_task_history(offset: int = 0) -> List[dict]:
    """Get the task history in blocks of 50.

    Args:
        offset (int, optional): The offset of the list.
            The higher the number, the deeper into history you go.

            Defaults to 0.

    Returns:
        List[dict]: The history entries.
    """
    result = get_db().execute(
        """
        SELECT
            task_name, display_title, run_at
        FROM task_history
        ORDER BY run_at DESC
        LIMIT 50
        OFFSET ?;
        """,
        (offset * 50,)
    ).fetchalldict()
    return result


def delete_task_history() -> None:
    "Delete the complete task history"
    LOGGER.info(f'Deleting task history')
    get_db().execute("DELETE FROM task_history;")
    # Consider committing here if not handled by calling context
    # commit()


def get_task_planning() -> List[dict]:
    """Get the planning of each interval task (interval, next run and last run)

    Returns:
        List[dict]: List of interval tasks and their planning
    """
    tasks = get_db().execute(
        """
        SELECT
            i.task_name, interval, next_run, run_at AS last_run
        FROM task_intervals i
        LEFT JOIN ( -- Use LEFT JOIN in case a task hasn't run yet
            SELECT
                task_name,
                MAX(run_at) AS run_at
            FROM task_history
            GROUP BY task_name
        ) h
        ON i.task_name = h.task_name;
        """
    ).fetchalldict()

    # To avoid circular import, fetch display names dynamically if needed
    # or store them alongside task_name in task_intervals table during setup.
    # Simple approach for now:
    temp_task_library = {} # Rebuild or import carefully
    try:
        from .handler import task_library as handler_task_library
        temp_task_library = handler_task_library
    except ImportError:
        # Log warning or handle gracefully if handler cannot be imported here
        pass

    for t in tasks:
        # Safely get display name
        task_class = temp_task_library.get(t['task_name'])
        t['display_name'] = getattr(task_class, 'display_title', t['task_name']) # Fallback

    return tasks