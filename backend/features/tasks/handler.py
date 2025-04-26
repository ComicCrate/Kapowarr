# -*- coding: utf-8 -*-

"""
Background task handling (queue management, execution).
"""

from __future__ import annotations

from threading import Thread, Timer
from time import sleep, time
from typing import Dict, List, Tuple, Type, Union

# Removed Flask import here as we'll use SERVER.app directly
# Use relative imports for Task base and definitions
from .base import Task
from .definitions import ( # Import all specific task classes
    AutoSearchIssue, MassRenameIssue, MassConvertIssue,
    AutoSearchVolume, RefreshAndScanVolume, MassRenameVolume, MassConvertVolume,
    UpdateAll, SearchAll
)
# Import other necessary modules
from backend.base.custom_exceptions import TaskNotDeletable, TaskNotFound
from backend.base.helpers import Singleton
from backend.base.logging import LOGGER
from backend.features.download_queue import DownloadHandler
# Import SERVER to access the main app context
from backend.internals.server import SERVER, WebSocket
from backend.internals.db import close_db, get_db, commit # Import commit if needed directly

# Build the task library dictionary
task_library: Dict[str, Type[Task]] = {
    c.action: c
    for c in (
        AutoSearchIssue, MassRenameIssue, MassConvertIssue,
        AutoSearchVolume, RefreshAndScanVolume, MassRenameVolume, MassConvertVolume,
        UpdateAll, SearchAll
    )
}


class TaskHandler(metaclass=Singleton):
    "Note: Singleton"

    queue: List[dict] = []
    task_interval_waiter: Union[Timer, None] = None

    def __init__(self) -> None:
        """Setup the handler"""
        # No need to create a separate context here,
        # we will use SERVER.app.app_context() when needed.
        return

    def __run_task(self, task: Task) -> None:
        """Run a task
        Args:
            task (Task): The task to run
        """
        LOGGER.debug(f'Running task {task.display_title}')
        # --- ADDED APP CONTEXT ---
        with SERVER.app.app_context():
            socket = WebSocket()
            try:
                result = task.run()
                cursor = get_db() # Now safe to call within context

                # Note in history
                cursor.execute(
                    "INSERT INTO task_history VALUES (?,?,?);",
                    (task.action, task.display_title, round(time()))
                )
                commit() # Commit DB changes

                if not task.stop:
                    if task.category == 'download' and result:
                        DownloadHandler().add_multiple(
                            (link, volume_id, issue_id, False)
                            for link, volume_id, issue_id in result
                        )

                    LOGGER.info(f'Finished task {task.display_title}')

            except Exception:
                LOGGER.exception('An error occurred while trying to run a task: ')
                task.message = 'AN ERROR OCCURRED'
                # Ensure WebSocket access is also context-safe if needed
                socket.update_task_status(task)
                sleep(1.5)

            finally:
                # close_db() is handled by app context teardown
                if not task.stop:
                    # Ensure WebSocket access is also context-safe if needed
                    socket.send_task_ended(task)
                    # Ensure queue access is thread-safe if modified elsewhere
                    if self.queue and self.queue[0]['task'] is task:
                         self.queue.pop(0)
                    self._process_queue()
        # --- END APP CONTEXT ---


    def _process_queue(self) -> None:
        """
        Handle the queue. In the case that there is something in the queue and
        it isn't already running, start the task. This can safely be called
        multiple times while a task is going or while there is nothing in the queue.
        """
        if not self.queue:
            return

        first_entry = self.queue[0]
        if first_entry['status'] != 'running':
            first_entry['status'] = 'running'
            if not first_entry['thread'].is_alive():
                 try:
                    first_entry['thread'].start()
                 except RuntimeError:
                    LOGGER.warning(f"Attempted to start task thread for {first_entry['task'].display_title} which was not startable.")
                    pass

    def add(self, task: Task) -> int:
        """Add a task to the queue"""
        LOGGER.debug(f'Adding task to queue: {task.display_title}')
        new_id = (self.queue[-1]['id'] + 1) if self.queue else 1
        task_data = {
            'task': task,
            'id': new_id,
            'status': 'queued',
            'thread': Thread( # Use direct Thread, __run_task now handles context
                target=self.__run_task,
                args=(task,),
                name=f"TaskRunner-{task.display_title}-{new_id}" # Specific thread name
            )
        }
        self.queue.append(task_data)
        LOGGER.info(f'Added task: {task.display_title} ({new_id})')
        WebSocket().send_task_added(task)
        self._process_queue()
        return new_id

    @staticmethod
    def task_for_volume_running(volume_id: int) -> bool:
        """Whether or not there is a task in the queue that targets the volume."""
        # Import locally if needed or ensure definitions are available
        from .definitions import UpdateAll, SearchAll
        return any(
            t
            for t in TaskHandler.queue # Access class variable directly
            if (isinstance(t['task'], (UpdateAll, SearchAll))
                or getattr(t['task'], 'volume_id', None) == volume_id)
        )

    def __check_intervals(self) -> None:
        "Check if any interval task needs to be run and add to queue if so"
        LOGGER.debug('Checking task intervals')
        # --- ADDED APP CONTEXT ---
        with SERVER.app.app_context():
            current_time = time()
            cursor = get_db() # Safe within context
            try:
                interval_tasks = cursor.execute(
                    "SELECT task_name, interval, next_run FROM task_intervals;"
                ).fetchall()

                if interval_tasks:
                    LOGGER.debug(f'Task intervals: {list(map(dict, interval_tasks))}')

                tasks_to_run = []
                updates_to_db = []

                for task_row in interval_tasks:
                     task = dict(task_row)
                     if task['next_run'] <= current_time:
                         task_class = task_library.get(task['task_name'])
                         if task_class:
                            if task_class is UpdateAll:
                                inst = task_class(allow_skipping=True)
                            else:
                                inst = task_class()
                            tasks_to_run.append(inst)

                            next_run = round(current_time + task['interval'])
                            updates_to_db.append((next_run, task['task_name']))
                         else:
                             LOGGER.warning(f"Task class not found in library for interval task: {task['task_name']}")

                # Add tasks outside the loop
                for task_instance in tasks_to_run:
                     self.add(task_instance)

                 # Update next_run in DB
                if updates_to_db:
                     cursor.executemany(
                         "UPDATE task_intervals SET next_run = ? WHERE task_name = ?;",
                         updates_to_db
                     )
                     commit() # Commit DB changes

            finally:
                # Context manager handles close_db
                pass
        # --- END APP CONTEXT ---

        # Schedule next check (outside context)
        self.handle_intervals()


    def handle_intervals(self) -> None:
        "Find next time an interval task needs to be run"
        next_run = None
        # --- ADDED APP CONTEXT ---
        with SERVER.app.app_context():
            cursor = get_db() # Safe within context
            try:
                next_run_row = cursor.execute(
                    "SELECT MIN(next_run) FROM task_intervals;"
                ).fetchone()
                next_run = next_run_row[0] if next_run_row and next_run_row[0] is not None else None
            finally:
                # Context manager handles close_db
                pass
        # --- END APP CONTEXT ---

        if next_run is None:
            LOGGER.info("No interval tasks scheduled.")
            return

        timedelta = max(1, next_run - round(time()))
        LOGGER.debug(f'Next interval task check in {timedelta} seconds')

        if self.task_interval_waiter and self.task_interval_waiter.is_alive():
            self.task_interval_waiter.cancel()

        self.task_interval_waiter = Timer(timedelta, self.__check_intervals)
        self.task_interval_waiter.name = "IntervalTaskScheduler"
        self.task_interval_waiter.daemon = True
        self.task_interval_waiter.start()


    def stop_handle(self) -> None:
        "Stop the task handler"
        # (Stop handle logic remains the same as previous version)
        LOGGER.debug('Stopping task handler')

        if self.task_interval_waiter and self.task_interval_waiter.is_alive():
            self.task_interval_waiter.cancel()
            self.task_interval_waiter = None

        if self.queue:
            current_task_entry = self.queue[0]
            current_task_entry['task'].stop = True
            if current_task_entry['thread'] and current_task_entry['thread'].is_alive():
                 current_task_entry['thread'].join(timeout=5.0)
                 if current_task_entry['thread'].is_alive():
                      LOGGER.warning(f"Task thread {current_task_entry['task'].display_title} did not stop gracefully.")

        self.queue.clear()


    def __format_entry(self, task_entry: dict) -> dict:
        """Format a queue entry for API response"""
        # (Format entry logic remains the same)
        task_instance = task_entry['task']
        return {
            'id': task_entry['id'],
            'action': task_instance.action,
            'display_title': task_instance.display_title,
            'status': task_entry['status'],
            'message': task_instance.message,
            'volume_id': task_instance.volume_id,
            'issue_id': task_instance.issue_id
        }

    def get_all(self) -> List[dict]:
        """Get all tasks in the queue"""
        # (Get all logic remains the same)
        return [self.__format_entry(t) for t in self.queue]

    def get_one(self, task_id: int) -> dict:
        """Get one task from the queue based on it's id"""
        # (Get one logic remains the same)
        for entry in self.queue:
            if entry['id'] == task_id:
                return self.__format_entry(entry)
        raise TaskNotFound


    def remove(self, task_id: int) -> None:
        """Remove a task from the queue"""
        # (Remove logic remains the same)
        task_entry_to_remove = None
        task_index = -1

        for index, entry in enumerate(self.queue):
            if entry['id'] == task_id:
                task_entry_to_remove = entry
                task_index = index
                break

        if task_entry_to_remove is None:
            raise TaskNotFound

        if task_index == 0 and task_entry_to_remove['status'] == 'running':
            raise TaskNotDeletable

        task_instance = task_entry_to_remove['task']

        task_instance.stop = True

        try:
            self.queue.pop(task_index)
            LOGGER.info(f'Removed task: {task_instance.display_title} ({task_id})')
            WebSocket().send_task_ended(task_instance) # Notify UI
        except IndexError:
             LOGGER.warning(f"Task {task_id} was already removed from queue.")

        self._process_queue()