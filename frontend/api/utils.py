# -*- coding: utf-8 -*-

from typing import Any, Dict, Tuple, Union
from backend.base.custom_exceptions import (
    BlocklistEntryNotFound, ClientDownloading, CredentialInvalid,
    CredentialNotFound, CVRateLimitReached, DownloadNotFound,
    ExternalClientNotFound, ExternalClientNotWorking, FileNotFound,
    FolderNotFound, InvalidComicVineApiKey, InvalidKeyValue, InvalidSettingKey,
    InvalidSettingModification, InvalidSettingValue, IssueNotFound,
    KeyNotFound, LogFileNotFound, RootFolderInUse, RootFolderInvalid,
    RootFolderNotFound, TaskForVolumeRunning, TaskNotDeletable, TaskNotFound,
    VolumeAlreadyAdded, VolumeDownloadedFor, VolumeNotFound
)
from backend.base.definitions import LibraryFilters, LibrarySorting
from backend.implementations.volumes import Library
from backend.internals.db_models import FilesDB
from backend.internals.server import SERVER, diffuse_timers
from backend.internals.settings import Settings
from backend.features.tasks import task_library
from flask import request

# Initialize Library instance (assuming it's stateless or manages state appropriately)
library = Library()

def return_api(
    result: Any,
    error: Union[str, None] = None,
    code: int = 200
) -> Tuple[Dict[str, Any], int]:
    """Helper function to format API responses."""
    return {'error': error, 'result': result}, code

def error_handler(method) -> Any:
    """Error handling decorator for API routes."""
    def wrapper(*args, **kwargs):
        try:
            return method(*args, **kwargs)
        except (
            BlocklistEntryNotFound, ClientDownloading, CredentialInvalid,
            CredentialNotFound, CVRateLimitReached, DownloadNotFound,
            ExternalClientNotFound, ExternalClientNotWorking, FileNotFound,
            FolderNotFound, InvalidComicVineApiKey, InvalidKeyValue, InvalidSettingKey,
            InvalidSettingModification, InvalidSettingValue, IssueNotFound,
            KeyNotFound, LogFileNotFound, RootFolderInUse, RootFolderInvalid,
            RootFolderNotFound, TaskForVolumeRunning, TaskNotDeletable, TaskNotFound,
            VolumeAlreadyAdded, VolumeDownloadedFor, VolumeNotFound
        ) as e:
            # Log the error appropriately here if desired
            # from backend.base.logging import LOGGER
            # LOGGER.error(f"API Error: {e.__class__.__name__} - {e.api_response}")
            return return_api(**e.api_response)
        # Consider adding a generic Exception handler for unexpected errors
        except Exception as e:
            # Log the full exception details
            # from backend.base.logging import LOGGER
            # LOGGER.exception("Unhandled API error occurred")
            return return_api(None, 'InternalServerError', 500)

    wrapper.__name__ = method.__name__
    return wrapper

def extract_key(request, key: str, check_existence: bool = True) -> Any:
    """Extract and format a value of a parameter from a request."""
    value: Any = request.values.get(key)
    if check_existence and value is None:
        raise KeyNotFound(key)

    if value is not None:
        # Check value based on key
        if key in ('volume_id', 'issue_id'):
            try:
                value = int(value)
                # Re-fetch library instance if necessary or pass it
                temp_library = Library() # Assuming Library can be instantiated per request or is thread-safe
                if key == 'volume_id':
                    temp_library.get_volume(value)
                else:
                    temp_library.get_issue(value)
            except (ValueError, TypeError, VolumeNotFound, IssueNotFound): # Added exceptions
                raise InvalidKeyValue(key, value)

        elif key == 'cmd':
            task = task_library.get(value) # Assuming task_library is accessible
            if task is None:
                raise TaskNotFound # Make sure TaskNotFound is defined and imported
            value = task # Return the task class/object itself

        elif key == 'api_key':
            # Consider fetching API key dynamically if it can change
            if not value or value != Settings().sv.api_key:
                raise InvalidKeyValue(key, value)

        elif key == 'sort':
            try:
                value = LibrarySorting[value.upper()]
            except KeyError:
                raise InvalidKeyValue(key, value)

        elif key == 'filter':
            try:
                value = LibraryFilters[value.upper()] if value else None
            except KeyError:
                raise InvalidKeyValue(key, value)

        elif key in ('root_folder_id', 'root_folder', 'offset', 'limit', 'index'):
            try:
                value = int(value)
            except (ValueError, TypeError):
                raise InvalidKeyValue(key, value)

        elif key in ('monitor', 'delete_folder', 'rename_files', 'only_english',
                    'limit_parent_folder', 'force_match', 'monitor_new_issues',
                    'custom_folder', 'special_version_locked', 'auto_search',
                    'blocklist'): # Added keys from usage
            lower_value = str(value).lower()
            if lower_value == 'true':
                value = True
            elif lower_value == 'false':
                value = False
            else:
                raise InvalidKeyValue(key, value)

        elif key in ('query', 'folder_filter', 'key', 'link', 'folder', # Added keys
                     'monitoring_scheme', 'volume_folder', 'special_version',
                     'web_link', 'web_title', 'web_sub_title', 'download_link',
                     'source', 'action', 'client_type', 'base_url', 'username',
                     'password', 'api_token', 'filepath'):
            if not isinstance(value, (str, int, float, bool)) or not value: # Allow non-empty values
                 # Ensure value is a basic type and not empty if it's a string
                if isinstance(value, str) and not value.strip():
                     raise InvalidKeyValue(key, value)
                # Allow non-string types if they are not considered "empty" (like 0 or False if intended)
                elif not isinstance(value, str) and value is None:
                     raise InvalidKeyValue(key, value)
            # No specific format change needed for these string/basic types unless required

        elif key == 'volume_ids': # Handle list type
             if not isinstance(value, list) or not all(isinstance(v, int) for v in value):
                 raise InvalidKeyValue(key, value)

        elif key == 'reason_id': # Handle specific conversion
             from backend.base.definitions import BlocklistReasonID
             try:
                 value = BlocklistReasonID(int(value))
             except (ValueError, KeyError):
                 raise InvalidKeyValue(key, value)

        # Add other specific key checks as needed

    else:
        # Default values if key not found and check_existence is False
        defaults = {
            'sort': LibrarySorting.TITLE,
            'filter': None,
            'monitor': True,
            'delete_folder': False,
            'offset': 0,
            'rename_files': False,
            'limit': 20,
            'only_english': True,
            'limit_parent_folder': False,
            'force_match': False,
            'monitor_new_issues': True,
            'auto_search': True,
            'blocklist': False,
            'filepath_filter': [] # Default for filepath_filter
        }
        if key in defaults:
            value = defaults[key]
        # Consider raising error if no default is defined for a non-checked key

    return value

def auth(method):
    """Authentication decorator."""
    def wrapper(*args, **kwargs):
        # from backend.base.logging import LOGGER # Import locally if needed
        # if not (
        #     request.method == 'GET'
        #     and (request.path in ('/api/system/tasks', '/api/activity/queue')
        #          or request.path.endswith('/cover'))
        # ):
        #     LOGGER.debug(f'{request.method} {request.path}') # Use logger

        try:
            extract_key(request, 'api_key')
        except (KeyNotFound, InvalidKeyValue):
            return return_api({}, 'ApiKeyInvalid', 401)

        diffuse_timers() # Assuming diffuse_timers is defined elsewhere

        result = method(*args, **kwargs)

        # if result[1] > 300:
            # LOGGER.debug(
            #     f'{request.method} {request.path} {result[1]} {result[0]}') # Use logger

        return result

    wrapper.__name__ = method.__name__
    return wrapper