# -*- coding: utf-8 -*-

from dataclasses import _MISSING_TYPE, asdict, dataclass, field
from json import dump, load, JSONDecodeError # Import JSONDecodeError
from logging import INFO
from os import urandom
from os.path import abspath, isdir, join, sep
from typing import Any, Dict, Mapping, List, Union

from backend.base.custom_exceptions import (FolderNotFound, InvalidSettingKey,
                                            InvalidSettingModification,
                                            InvalidSettingValue)
from backend.base.definitions import (BaseEnum, GCDownloadSource,
                                      RestartVersion, SeedingHandling)
from backend.base.files import (folder_is_inside_folder,
                                folder_path, uppercase_drive_letter)
from backend.base.helpers import (CommaList, Singleton, force_suffix,
                                  get_python_version, normalize_base_url,
                                  reversed_tuples)
from backend.base.logging import LOGGER, set_log_level
from backend.internals.db import commit, get_db
from backend.internals.db_migration import get_latest_db_version


@dataclass(frozen=True)
class SettingsValues:
    database_version: int = get_latest_db_version()
    log_level: int = INFO
    auth_password: str = ''
    comicvine_api_keys: List[str] = field(default_factory=list) # Changed to List[str]
    api_key: str = ''

    host: str = '0.0.0.0'
    port: int = 5656
    url_base: str = ''
    backup_host: str = '0.0.0.0'
    backup_port: int = 5656
    backup_url_base: str = ''

    rename_downloaded_files: bool = True
    volume_folder_naming: str = join(
        '{series_name}', 'Volume {volume_number} ({year})'
    )
    file_naming: str = '{series_name} ({year}) Volume {volume_number} Issue {issue_number}'
    file_naming_empty: str = '{series_name} ({year}) Volume {volume_number} Issue {issue_number}'
    file_naming_special_version: str = '{series_name} ({year}) Volume {volume_number} {special_version}'
    file_naming_vai: str = '{series_name} ({year}) Volume {issue_number}'

    long_special_version: bool = False
    volume_padding: int = 2
    issue_padding: int = 3

    service_preference: CommaList = field(default_factory=lambda: CommaList(
        (s.value for s in GCDownloadSource._member_map_.values())
    ))
    download_folder: str = folder_path('temp_downloads')
    concurrent_direct_downloads: int = 1
    failing_torrent_timeout: int = 0
    seeding_handling: SeedingHandling = SeedingHandling.COPY
    delete_completed_torrents: bool = True

    convert: bool = False
    extract_issue_ranges: bool = False
    format_preference: CommaList = field(default_factory=lambda: CommaList(''))

    flaresolverr_base_url: str = ''

    def to_dict(self) -> Dict[str, Any]:
        # Convert list of keys back to a list for the API response
        settings_dict = asdict(self)
        settings_dict['comicvine_api_keys'] = self.comicvine_api_keys # Use the list directly
        return {
            k: v if not isinstance(v, BaseEnum) else v.value
            for k, v in settings_dict.items()
            if not k.startswith('backup_')
        }


about_data = {
    'version': 'v1.2.0',
    'python_version': get_python_version(),
    'database_version': get_latest_db_version(),
    'database_location': None, # Get's filled in by db.set_db_location()
    'data_folder': folder_path()
}


task_intervals = {
    # If there are tasks that should be run at the same time,
    # but per se after each other, put them in that order in the dict.
    'update_all': 3600, # every hour
    'search_all': 86400 # every day
}


class Settings(metaclass=Singleton):
    def __init__(self) -> None:
        self._insert_missing_settings()
        self._fetch_settings()
        return

    def _insert_missing_settings(self) -> None:
        "Insert any missing keys from the settings into the database."
        # When inserting, convert the list of keys to a string for storage
        default_values_dict = asdict(SettingsValues())
        if isinstance(default_values_dict.get('comicvine_api_keys'), list):
            default_values_dict['comicvine_api_keys'] = ','.join(default_values_dict['comicvine_api_keys']) # Store as comma-separated string

        get_db().executemany(
            "INSERT OR IGNORE INTO config(key, value) VALUES (?, ?);",
            default_values_dict.items()
        )
        commit()
        return

    def _fetch_settings(self) -> None:
        "Load the settings from the database into the cache."
        db_values = {
            k: v
            for k, v in get_db().execute(
                "SELECT key, value FROM config;"
            )
            if k in SettingsValues.__dataclass_fields__
        }

        # Handle deserialization for list and enum types
        for cl_key in ('format_preference', 'service_preference'):
            db_values[cl_key] = CommaList(db_values.get(cl_key, '')) # Use get with default for safety

        for en_key, en in (
            ('seeding_handling', SeedingHandling),
        ):
            # Safely get and convert enum values
            db_values[en_key] = en[db_values.get(en_key, '').upper()] if db_values.get(en_key) else SettingsValues.__dataclass_fields__[en_key].default


        # Handle deserialization for the list of ComicVine API keys
        comicvine_keys_str = db_values.get('comicvine_api_keys', '')
        if isinstance(comicvine_keys_str, str):
            db_values['comicvine_api_keys'] = [key.strip() for key in comicvine_keys_str.split(',') if key.strip()] # Convert comma-separated string to list
        else:
             # Handle unexpected data type in DB for comicvine_api_keys
             LOGGER.warning(f"Unexpected data type for comicvine_api_keys in DB: {type(comicvine_keys_str)}. Defaulting to empty list.")
             db_values['comicvine_api_keys'] = []


        self.__cached_values = SettingsValues(**{
            k: v for k, v in db_values.items()
            if k in SettingsValues.__dataclass_fields__ # Only pass fields defined in the dataclass
        })
        return


    def get_settings(self) -> SettingsValues:
        """Get the settings from the cache.

        Returns:
            SettingsValues: The settings.
        """
        return self.__cached_values

    # Alias, better in one-liners
    # sv = Settings Values
    @property
    def sv(self) -> SettingsValues:
        """Get the settings from the cache.

        Returns:
            SettingsValues: The settings.
        """
        return self.__cached_values

    def __getitem__(self, __name: str) -> Any:
        """Get the value of the given setting key.

        Args:
            __name (str): The key of the setting.

        Raises:
            AttributeError: Key is not a setting key.

        Returns:
            Any: The value of the setting.
        """
        try:
            return getattr(self.__cached_values, __name)
        except AttributeError:
            raise InvalidSettingKey(__name)


    def update(
        self,
        data: Mapping[str, Any]
    ) -> None:
        """Change the settings, in a `dict.update()` type of way.

        Args:
            data (Mapping[str, Any]): The keys and their new values.

        Raises:
            InvalidSettingKey: Key is not allowed or unknown.
            InvalidSettingValue: Value of the key is not allowed.
            InvalidSettingModification: Key can not be modified this way.
            FolderNotFound: Folder not found.
        """
        from backend.implementations.naming import (NAMING_MAPPING,
                                                    check_mock_filename)

        formatted_data = {}
        for key, value in data.items():
            formatted_data[key] = self.__format_value(key, value)

        if any(
            key in formatted_data
            for key in NAMING_MAPPING
        ):
            # Changes to naming schemes
            check_mock_filename(**{
                key: formatted_data.get(key)
                for key in NAMING_MAPPING
            })

        hosting_changes = any(
            s in data
            and formatted_data[s] != getattr(self.get_settings(), s)
            for s in ('host', 'port', 'url_base')
        )

        if hosting_changes:
            self.backup_hosting_settings()

        # Convert list of keys back to string for database storage before updating
        if 'comicvine_api_keys' in formatted_data and isinstance(formatted_data['comicvine_api_keys'], list):
             formatted_data['comicvine_api_keys'] = ','.join(formatted_data['comicvine_api_keys'])


        get_db().executemany(
            "UPDATE config SET value = ? WHERE key = ?;",
            reversed_tuples(formatted_data.items())
        )
        commit() # Commit changes to DB


        for key, handler in (
            ('url_base', update_manifest),
            ('log_level', set_log_level)
        ):
            if (
                key in data
                and formatted_data.get(key) is not None # Check if key exists in formatted_data and is not None
                and formatted_data[key] != getattr(self.get_settings(), key)
            ):
                # Pass the original value before string conversion if the handler expects the original type
                handler_value = data.get(key) if key == 'log_level' else formatted_data[key]
                handler(handler_value)


        self._fetch_settings() # Reload settings from DB after update

        LOGGER.info(f'Settings changed: {formatted_data}')

        if hosting_changes:
            from backend.internals.server import SERVER
            SERVER.restart(
                RestartVersion.HOSTING_CHANGES
            )

        # If ComicVine API keys were updated, potentially re-initialize ComicVine
        if 'comicvine_api_keys' in data:
             from backend.implementations.comicvine import ComicVine
             # Re-initialize the singleton instance with the new keys
             # This might require modifying the ComicVine singleton or how it gets keys
             # For now, relying on the next time ComicVine is instantiated to get fresh settings.
             # A more robust solution might involve a method in ComicVine to update keys.
             pass


        return

    def __setitem__(self, __name: str, __value: Any) -> None:
        """Change the value of a setting.

        Args:
            __name (str): The key of the setting.
            __value (Any): The new value.

        Raises:
            InvalidSettingKey: Key is not allowed or unknown.
            InvalidSettingValue: Value of the key is not allowed.
            InvalidSettingModification: Key can not be modified this way.
            FolderNotFound: Folder not found.
        """
        self.update({__name: __value})
        return

    def reset(self, key: str) -> None:
        """Reset the value of the key to the default value.

        Args:
            key (str): The key of which to reset the value.

        Raises:
            InvalidSettingKey: The key is not valid or unknown.
        """
        LOGGER.debug(f'Setting reset: {key}')

        if key not in SettingsValues.__dataclass_fields__:
            raise InvalidSettingKey(key)

        # Get the default value for the field
        field_info = SettingsValues.__dataclass_fields__[key]
        if not isinstance(field_info.default_factory, _MISSING_TYPE):
            default_value = field_info.default_factory()
        else:
            default_value = field_info.default

        # Update the setting with the default value
        self[key] = default_value

        return

    def generate_api_key(self) -> None:
        "Generate a new api key"
        LOGGER.debug('Generating new api key')

        api_key = urandom(16).hex()
        get_db().execute(
            "UPDATE config SET value = ? WHERE key = 'api_key';",
            (api_key,)
        )
        commit() # Commit the new API key to DB
        self._fetch_settings() # Reload settings to cache the new API key

        LOGGER.info(f'Setting api key regenerated: {api_key}')
        return

    def backup_hosting_settings(self) -> None:
        "Backup the hosting settings in the database."
        s = self.get_settings()
        backup_settings = {
            'backup_host': s.host,
            'backup_port': s.port,
            'backup_url_base': s.url_base
        }
        # Use self.update for consistent validation and DB update
        self.update(backup_settings)
        return

    def __format_value(self, key: str, value: Any) -> Any:
        """Check if the value of a setting is allowed and convert if needed.

        Args:
            key (str): Key of setting.
            value (Any): Value of setting.

        Raises:
            InvalidSettingKey: Key is invalid or unknown.
            InvalidSettingValue: Value is not allowed.
            InvalidSettingModification: Key can not be modified this way.
            FolderNotFound: Folder not found.

        Returns:
            Any: (Converted) Setting value.
        """
        converted_value = value

        if key not in SettingsValues.__dataclass_fields__:
            raise InvalidSettingKey(key)

        # Handle specific keys with custom validation or conversion
        if key == 'api_key':
            raise InvalidSettingModification(key, 'POST /settings/api_key') # Prevent changing via PUT

        # Handle list type for comicvine_api_keys
        if key == 'comicvine_api_keys':
            if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
                raise InvalidSettingValue(key, value, "Expected a list of strings.")
            # Basic validation for each key format (optional, depends on desired strictness)
            # For now, just ensure they are non-empty strings after stripping
            validated_keys = [k.strip() for k in value if k.strip()]
            # You might add format validation here, e.g., checking length or character set
            # Example: if any key doesn't match a regex pattern, raise InvalidSettingValue
            converted_value = validated_keys # Keep as list here, convert to string before DB update


        # Handle CommaList types
        elif (SettingsValues.__dataclass_fields__[key].type is CommaList
            and isinstance(value, list)): # Expecting a list input for CommaList settings
            # CommaList constructor handles internal formatting
             converted_value = CommaList(value)


        # Handle Enum types
        elif issubclass(SettingsValues.__dataclass_fields__[key].type, BaseEnum):
            try:
                # Convert input value (string) to the corresponding Enum member
                converted_value = SettingsValues.__dataclass_fields__[key].type(value)
            except ValueError:
                # If value is not a valid Enum member, raise an error
                raise InvalidSettingValue(key, value, f"Invalid value for enum {SettingsValues.__dataclass_fields__[key].type.__name__}.")


        # Basic type check against the dataclass field type (after potential custom conversions)
        # Skip this check for comicvine_api_keys since we are temporarily keeping it as a list
        if key != 'comicvine_api_keys' and not isinstance(converted_value, SettingsValues.__dataclass_fields__[key].type):
             raise InvalidSettingValue(key, value, f"Value type mismatch. Expected {SettingsValues.__dataclass_fields__[key].type.__name__}.")


        # Handle specific keys with value constraints or side effects
        if key == 'port' and not 0 < converted_value <= 65_535:
            raise InvalidSettingValue(key, value, "Port number must be between 1 and 65535.")

        elif key == 'url_base':
            # Ensure url_base is correctly formatted
            if converted_value:
                converted_value = ('/' + converted_value.lstrip('/')).rstrip('/')
            # No validation needed here, the update logic handles applying it

        # The IndentationError is likely happening here, check alignment of these elif/else blocks
        elif key == 'download_folder':
            # Validate download_folder path and its relation to root folders
            if not isinstance(converted_value, str) or not isdir(converted_value):
                 raise FolderNotFound(f"Download folder path not found or is not a directory: {converted_value}")

            converted_value = uppercase_drive_letter(
                force_suffix(abspath(converted_value))
            )

            from backend.implementations.root_folders import RootFolders
            for rf in RootFolders().get_all():
                if (
                    folder_is_inside_folder(rf.folder, converted_value)
                    or folder_is_inside_folder(converted_value, rf.folder)
                ):
                    raise InvalidSettingValue(key, value, "Download folder cannot be inside or contain a root folder.")

        elif key == 'concurrent_direct_downloads' and converted_value <= 0:
            raise InvalidSettingValue(key, value, "Concurrent direct downloads must be at least 1.")

        elif key == 'failing_torrent_timeout' and converted_value < 0:
            raise InvalidSettingValue(key, value, "Failing torrent timeout cannot be negative.")

        elif key == 'volume_padding' and not 1 <= converted_value <= 3:
            raise InvalidSettingValue(key, value, "Volume padding must be between 1 and 3.")

        elif key == 'issue_padding' and not 1 <= converted_value <= 4:
            raise InvalidSettingValue(key, value, "Issue padding must be between 1 and 4.")

        elif key == 'format_preference':
            # Validate format preference list against available formats
            from backend.implementations.conversion import FileConversionHandler
            available = FileConversionHandler.get_available_formats()
            for entry in converted_value: # converted_value is a CommaList here
                if entry not in available and entry != '': # Allow empty string for 'No Conversion' implicitly
                    raise InvalidSettingValue(key, value, f"Invalid format '{entry}' in format preference.")
            # CommaList handles duplicates internally if needed

        elif key == 'service_preference':
             # Validate service preference list against allowed sources
             available_values = [s.value for s in GCDownloadSource._member_map_.values()]
             for entry in converted_value: # converted_value is a CommaList here
                 if entry not in available_values:
                      raise InvalidSettingValue(key, value, f"Invalid service '{entry}' in service preference.")
             # Ensure all available services are present in the preference list (optional, but good for completeness)
             # For entry in available_values:
             #     if entry not in converted_value:
             #          # Decide how to handle missing services - add them to the end? or raise error?
             #          pass


        elif key == 'flaresolverr_base_url':
            # Validate and handle FlareSolverr URL changes
            from backend.implementations.flaresolverr import FlareSolverr
            fs = FlareSolverr()
            original_fs_base_url = fs.base_url # Store current state

            if converted_value: # If the new value is not empty
                try:
                    converted_value = normalize_base_url(converted_value)
                    # Attempt to enable FS with the new URL to test it
                    if not fs.enable_flaresolverr(converted_value):
                        raise InvalidSettingValue(key, value, f"Could not connect to FlareSolverr at {converted_value}. Check the URL and if FlareSolverr is running.")
                    # If successful, fs is now updated in the singleton
                except Exception as e:
                    # Catch any errors during normalization or enable attempt
                    raise InvalidSettingValue(key, value, f"Error setting FlareSolverr URL: {e}") from e
            else: # If the new value is empty, disable FS if it was running
                 if original_fs_base_url:
                      fs.disable_flaresolverr()
                 # converted_value remains ''

            # If FS was running on a different URL and the new one failed, re-enable the old one
            # This rollback logic is handled within the update method after __format_value returns

        else:
            # Handle naming format strings
            from backend.implementations.naming import (NAMING_MAPPING,
                                                        check_format)
            if key in NAMING_MAPPING:
                if not isinstance(converted_value, str):
                     raise InvalidSettingValue(key, value, "Naming format must be a string.")
                converted_value = converted_value.strip().strip(sep)
                if not check_format(converted_value, key):
                    raise InvalidSettingValue(key, value, f"Invalid format string for '{key}'. Contains disallowed characters or invalid variables.")


        return converted_value


def update_manifest(url_base: str) -> None:
    """Update the url's in the manifest file.
    Needs to happen when url base changes.

    Args:
        url_base (str): The url base to use in the file.
    """
    filename = folder_path('frontend', 'static', 'json', 'pwa_manifest.json')

    try:
        with open(filename, 'r') as f:
            manifest = load(f)
            manifest['start_url'] = url_base + '/'
            manifest['icons'][0]['src'] = f'{url_base}/static/img/favicon.svg'

        with open(filename, 'w') as f:
            dump(manifest, f, indent=4)
    except (FileNotFoundError, JSONDecodeError) as e:
        LOGGER.error(f"Failed to update manifest file {filename}: {e}")


    return