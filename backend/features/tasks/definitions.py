# -*- coding: utf-8 -*-

"""
Specific task implementations.
"""

from __future__ import annotations

from typing import List, Tuple, Union

# Use relative import for the base Task class
from .base import Task
# Import necessary backend functions and classes directly
from backend.base.custom_exceptions import InvalidComicVineApiKey
from backend.features.search import auto_search
from backend.implementations.conversion import mass_convert
from backend.implementations.naming import mass_rename
from backend.implementations.volumes import Issue, Volume, refresh_and_scan
from backend.internals.db import get_db
from backend.internals.server import WebSocket

# =====================
# Issue tasks
# =====================

class AutoSearchIssue(Task):
    "Do an automatic search for an issue"

    stop = False
    message = ''
    action = 'auto_search_issue'
    display_title = 'Auto Search'
    category = 'download'

    @property
    def volume_id(self) -> int:
        return self._volume_id

    @property
    def issue_id(self) -> int:
        return self._issue_id

    def __init__(self, volume_id: int, issue_id: int) -> None:
        """Create the task

        Args:
            volume_id (int): The id of the volume in which the issue is
            issue_id (int): The id of the issue to search for
        """
        self._volume_id = volume_id
        self._issue_id = issue_id
        return

    def run(self) -> List[Tuple[str, int, Union[int, None]]]:
        volume_title = Volume(self._volume_id).vd.title
        issue_number = Issue(self._issue_id).get_data().issue_number
        self.message = f'Searching for {volume_title} #{issue_number}'
        WebSocket().update_task_status(self)

        # Get search results and download them
        results = auto_search(self._volume_id, self._issue_id)
        if results:
            # Ensure result keys match expected tuple structure if needed
            # Assuming auto_search returns dicts with 'link' key
            return [
                (result['link'], self._volume_id, self._issue_id)
                for result in results
            ]
        return []


class MassRenameIssue(Task):
    "Trigger a mass rename for an issue"

    stop = False
    message = ''
    action = 'mass_rename_issue'
    display_title = 'Mass Rename'
    category = ''

    @property
    def volume_id(self) -> int:
        return self._volume_id

    @property
    def issue_id(self) -> int:
        return self._issue_id

    def __init__(
        self,
        volume_id: int,
        issue_id: int,
        filepath_filter: List[str] = []
    ) -> None:
        """Create the task

        Args:
            volume_id (int): The ID of the volume for which to perform the task.
            issue_id (int): The ID of the issue for which to perform the task.
            filepath_filter (List[str], optional): Only rename files in this
            list.
                Defaults to [].
        """
        self._volume_id = volume_id
        self._issue_id = issue_id
        self.filepath_filter = filepath_filter
        return

    def run(self) -> None:
        volume_title = Volume(self._volume_id).vd.title
        issue_number = Issue(self._issue_id).get_data().issue_number
        self.message = f'Renaming files for {volume_title} #{issue_number}'
        WebSocket().update_task_status(self)

        mass_rename(
            self._volume_id,
            self._issue_id,
            filepath_filter=self.filepath_filter,
            update_websocket=True
        )
        return


class MassConvertIssue(Task):
    "Trigger a mass convert for an issue"

    stop = False
    message = ''
    action = 'mass_convert_issue'
    display_title = 'Mass Convert'
    category = ''

    @property
    def volume_id(self) -> int:
        return self._volume_id

    @property
    def issue_id(self) -> int:
        return self._issue_id

    def __init__(
        self,
        volume_id: int,
        issue_id: int,
        filepath_filter: List[str] = []
    ) -> None:
        """Create the task

        Args:
            volume_id (int): The ID of the volume for which to perform the task.
            issue_id (int): The ID of the issue for which to perform the task.
            filepath_filter (List[str], optional): Only rename files in this
            list.
                Defaults to [].
        """
        self._volume_id = volume_id
        self._issue_id = issue_id
        self.filepath_filter = filepath_filter
        return

    def run(self) -> None:
        volume_title = Volume(self._volume_id).vd.title
        issue_number = Issue(self._issue_id).get_data().issue_number
        self.message = f'Converting files for {volume_title} #{issue_number}'
        WebSocket().update_task_status(self)

        mass_convert(
            self._volume_id,
            self._issue_id,
            filepath_filter=self.filepath_filter,
            update_websocket=True
        )
        return

# =====================
# Volume tasks
# =====================

class AutoSearchVolume(Task):
    "Do an automatic search for a volume"

    stop = False
    message = ''
    action = 'auto_search'
    display_title = 'Auto Search'
    category = 'download'

    @property
    def volume_id(self) -> int:
        return self._volume_id

    @property
    def issue_id(self) -> None:
        return None

    def __init__(self, volume_id: int) -> None:
        """Create the task

        Args:
            volume_id (int): The id of the volume to search for
        """
        self._volume_id = volume_id
        return

    def run(self) -> List[Tuple[str, int, Union[int, None]]]:
        volume_title = Volume(self._volume_id).vd.title
        self.message = f'Searching for {volume_title}'
        WebSocket().update_task_status(self)

        # Get search results and download them
        results = auto_search(self._volume_id)
        if results:
            # Ensure result keys match expected tuple structure if needed
            # Assuming auto_search returns dicts with 'link' key
            return [
                (result['link'], self._volume_id, None)
                for result in results
            ]
        return []


class RefreshAndScanVolume(Task):
    "Trigger a refresh and scan for a volume"

    stop = False
    message = ''
    action = 'refresh_and_scan'
    display_title = 'Refresh And Scan'
    category = ''

    @property
    def volume_id(self) -> int:
        return self._volume_id

    @property
    def issue_id(self) -> None:
        return None

    def __init__(self, volume_id: int) -> None:
        """Create the task

        Args:
            volume_id (int): The id of the volume for which to perform the task
        """
        self._volume_id = volume_id
        return

    def run(self) -> None:
        volume_title = Volume(self._volume_id).vd.title
        self.message = f'Updating info on {volume_title}'
        WebSocket().update_task_status(self)

        try:
            refresh_and_scan(self._volume_id)
        except InvalidComicVineApiKey:
            pass # Or log a warning, depending on desired behavior
        return


class MassRenameVolume(Task):
    "Trigger a mass rename for a volume"

    stop = False
    message = ''
    action = 'mass_rename'
    display_title = 'Mass Rename'
    category = ''

    @property
    def volume_id(self) -> int:
        return self._volume_id

    @property
    def issue_id(self) -> None:
        return None

    def __init__(
        self,
        volume_id: int,
        filepath_filter: List[str] = []
    ) -> None:
        """Create the task

        Args:
            volume_id (int): The ID of the volume for which to perform the task.
            filepath_filter (List[str], optional): Only rename files in this
            list.
                Defaults to [].
        """
        self._volume_id = volume_id
        self.filepath_filter = filepath_filter
        return

    def run(self) -> None:
        volume_title = Volume(self._volume_id).vd.title
        self.message = f'Renaming files for {volume_title}'
        WebSocket().update_task_status(self)

        mass_rename(
            self._volume_id,
            filepath_filter=self.filepath_filter,
            update_websocket=True
        )
        return


class MassConvertVolume(Task):
    "Trigger a mass convert for a volume"

    stop = False
    message = ''
    action = 'mass_convert'
    display_title = 'Mass Convert'
    category = ''

    @property
    def volume_id(self) -> int:
        return self._volume_id

    @property
    def issue_id(self) -> None:
        return None

    def __init__(
        self,
        volume_id: int,
        filepath_filter: List[str] = []
    ) -> None:
        """Create the task

        Args:
            volume_id (int): The ID of the volume for which to perform the task.
            filepath_filter (List[str], optional): Only convert files in this
            list.
                Defaults to [].
        """
        self._volume_id = volume_id
        self.filepath_filter = filepath_filter
        return

    def run(self) -> None:
        volume_title = Volume(self._volume_id).vd.title
        self.message = f'Converting files for {volume_title}'
        WebSocket().update_task_status(self)

        mass_convert(
            self._volume_id,
            filepath_filter=self.filepath_filter,
            update_websocket=True
        )
        return

# =====================
# Library tasks
# =====================

class UpdateAll(Task):
    "Trigger a refresh and scan for each volume in the library"

    stop = False
    message = ''
    action = 'update_all'
    display_title = 'Update All'
    category = ''

    @property
    def volume_id(self) -> None:
        return None

    @property
    def issue_id(self) -> None:
        return None

    def __init__(self, allow_skipping: bool = False) -> None:
        """Create the task

        Args:
            allow_skipping (bool, optional): Skip volumes that have been updated in the last 24 hours.
                Defaults to False.
        """
        self.allow_skipping = allow_skipping
        return

    def run(self) -> None:
        self.message = f'Updating info on all volumes'
        WebSocket().update_task_status(self)

        try:
            refresh_and_scan(
                update_websocket=True,
                allow_skipping=self.allow_skipping
            )
        except InvalidComicVineApiKey:
            pass # Or log a warning
        return


class SearchAll(Task):
    "Trigger an automatic search for each volume in the library"

    stop = False
    message = ''
    action = 'search_all'
    display_title = 'Search All'
    category = 'download'

    @property
    def volume_id(self) -> None:
        return None

    @property
    def issue_id(self) -> None:
        return None

    def __init__(self) -> None:
        return

    def run(self) -> List[Tuple[str, int, Union[int, None]]]:
        cursor = get_db(force_new=True) # Get new cursor for potentially long task
        cursor.execute(
            "SELECT id, title FROM volumes WHERE monitored = 1;"
        )
        downloads: List[Tuple[str, int, Union[int, None]]] = []
        ws = WebSocket()
        for volume_id, volume_title in cursor:
            if self.stop:
                break
            self.message = f'Searching for {volume_title}'
            ws.update_task_status(self)
            # Get search results and download them
            results = auto_search(volume_id)
            if results:
                downloads += [
                    # Ensure result keys match expected tuple structure if needed
                    # Assuming auto_search returns dicts with 'link' key
                    (result['link'], volume_id, None)
                    for result in results
                ]
        return downloads