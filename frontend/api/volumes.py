# -*- coding: utf-8 -*-

from flask import Blueprint, request, send_file
from asyncio import run
from typing import Dict, Any

from backend.base.custom_exceptions import KeyNotFound, InvalidKeyValue
from backend.base.definitions import VolumeData, SpecialVersion, MonitorScheme
from backend.implementations.comicvine import ComicVine
from backend.implementations.naming import generate_volume_folder_name
from backend.implementations.volumes import Library
from .utils import return_api, error_handler, auth, extract_key, library # Use relative import

volumes_api = Blueprint('volumes_api', __name__)

@volumes_api.route('/search', methods=['GET', 'POST'])
@error_handler
@auth
def api_volumes_search():
    if request.method == 'GET':
        query = extract_key(request, 'query')
        # Assuming ComicVine().search_volumes is async
        search_results = run(ComicVine().search_volumes(query))
        # Remove cover data before sending response if needed
        for r in search_results:
            r.pop("cover", None) # Safely remove 'cover' if it exists
        return return_api(search_results)

    elif request.method == 'POST':
        data: Dict[str, Any] = request.get_json()
        required_keys = ('comicvine_id', 'title', 'year', 'volume_number', 'publisher')
        if not all(key in data for key in required_keys):
            missing = [key for key in required_keys if key not in data]
            raise KeyNotFound(f"Missing keys: {', '.join(missing)}")

        try:
            # Basic type checking for required keys
            cv_id = int(data['comicvine_id'])
            year = int(data['year']) if data['year'] is not None else None
            vol_num = int(data['volume_number']) if data['volume_number'] is not None else 1
        except (TypeError, ValueError):
             raise InvalidKeyValue("Invalid type for comicvine_id, year, or volume_number")


        # Create VolumeData object (assuming default values are handled within VolumeData)
        # Note: ID is 0, description, site_url, monitored etc. are defaults
        #       special_version needs careful handling based on input
        try:
            special_version_input = data.get('special_version')
            sv = SpecialVersion(special_version_input) if special_version_input else None
        except ValueError:
             raise InvalidKeyValue('special_version', special_version_input)


        vd = VolumeData(
            id=0, # Placeholder ID
            comicvine_id=cv_id,
            title=str(data['title']),
            alt_title=str(data['title']), # Assuming alt_title defaults to title initially
            year=year,
            publisher=str(data['publisher']),
            volume_number=vol_num,
            description="", # Default
            site_url="",    # Default
            monitored=True, # Default
            monitor_new_issues=True, # Default
            root_folder=1,  # Default or requires input? Assuming 1 for now
            folder="",      # To be generated
            custom_folder=False, # Default
            special_version=sv,
            special_version_locked=False, # Default
            last_cv_fetch=0 # Default
        )

        folder = generate_volume_folder_name(vd)
        return return_api({'folder': folder})


@volumes_api.route('', methods=['GET', 'POST']) # Changed route base
@error_handler
@auth
def api_volumes():
    if request.method == 'GET':
        query = extract_key(request, 'query', False)
        sort = extract_key(request, 'sort', False)
        filter_param = extract_key(request, 'filter', False) # Renamed to avoid conflict
        if query:
            volumes = library.search(query, sort, filter_param)
        else:
            volumes = library.get_public_volumes(sort, filter_param)
        return return_api(volumes)

    elif request.method == 'POST':
        data: dict = request.get_json()

        # Extract and validate parameters using extract_key for consistency
        comicvine_id = extract_key(data, 'comicvine_id')
        root_folder_id = extract_key(data, 'root_folder_id')
        monitor = extract_key(data, 'monitor', False) # Default is True via extract_key
        monitoring_scheme_str = data.get('monitoring_scheme', 'all') # Default 'all'
        monitor_new_issues = extract_key(data, 'monitor_new_issues', False) # Default True
        volume_folder = data.get('volume_folder') or None # Allow None or empty string -> None
        auto_search = extract_key(data, 'auto_search', False) # Default True
        special_version_str = data.get('special_version')

        try:
            monitoring_scheme = MonitorScheme(monitoring_scheme_str)
        except ValueError:
            raise InvalidKeyValue("monitoring_scheme", monitoring_scheme_str)

        sv = None
        if special_version_str and special_version_str != 'auto':
            try:
                sv = SpecialVersion(special_version_str)
            except ValueError:
                raise InvalidKeyValue('special_version', special_version_str)

        volume_id = library.add(
            comicvine_id, root_folder_id, monitor, monitoring_scheme,
            monitor_new_issues, volume_folder, sv, auto_search
        )
        # Fetch the newly added volume info to return
        new_volume_info = library.get_volume(volume_id).get_public_keys()
        return return_api(new_volume_info, code=201)


@volumes_api.route('/stats', methods=['GET'])
@error_handler
@auth
def api_volumes_stats():
    result = library.get_stats()
    return return_api(result)


@volumes_api.route('/<int:id>', methods=['GET', 'PUT', 'DELETE'])
@error_handler
@auth
def api_volume(id: int):
    volume = library.get_volume(id) # Raises VolumeNotFound if not found

    if request.method == 'GET':
        volume_info = volume.get_public_keys()
        return return_api(volume_info)

    elif request.method == 'PUT':
        edit_info: Dict[str, Any] = request.get_json()
        update_data = {}

        # Specific handlers first
        if 'root_folder' in edit_info:
             # Validation can happen inside change_root_folder or here
             # Assuming change_root_folder handles validation & persistence
            try:
                 new_rf_id = int(edit_info['root_folder'])
                 volume.change_root_folder(new_rf_id) # Handle potential errors
            except (ValueError, TypeError):
                 raise InvalidKeyValue('root_folder', edit_info['root_folder'])
            except Exception as e: # Catch specific errors from change_root_folder
                 # Log error e
                 return return_api(None, f"Failed changing root folder: {e}", 400) # Or appropriate error


        if 'volume_folder' in edit_info:
             # Assuming change_volume_folder handles validation & persistence
             try:
                 volume.change_volume_folder(edit_info['volume_folder']) # Handle potential errors
             except Exception as e:
                 # Log error e
                 return return_api(None, f"Failed changing volume folder: {e}", 400) # Or appropriate error


        if 'monitoring_scheme' in edit_info:
            try:
                scheme_str = edit_info['monitoring_scheme']
                if not scheme_str: # Allow empty string to mean "don't apply"
                     pass
                else:
                     monitoring_scheme = MonitorScheme(scheme_str)
                     volume.apply_monitor_scheme(monitoring_scheme)
            except ValueError:
                raise InvalidKeyValue('monitoring_scheme', edit_info['monitoring_scheme'])
            except Exception as e: # Catch specific errors from apply_monitor_scheme
                 # Log error e
                 return return_api(None, f"Failed applying monitoring scheme: {e}", 400) # Or appropriate error

        # General updates - filter allowed keys
        allowed_update_keys = ['monitored', 'monitor_new_issues', 'special_version', 'special_version_locked'] # Add others if applicable
        for key in allowed_update_keys:
            if key in edit_info:
                # Add validation logic here if necessary before adding to update_data
                if key == 'special_version':
                     try:
                         sv_input = edit_info[key]
                         update_data[key] = SpecialVersion(sv_input) if sv_input is not None else None
                     except ValueError:
                          raise InvalidKeyValue(key, sv_input)
                elif key in ('monitored', 'monitor_new_issues', 'special_version_locked'):
                     if not isinstance(edit_info[key], bool):
                         raise InvalidKeyValue(key, edit_info[key])
                     update_data[key] = edit_info[key]
                # Add validation for other keys

        # Apply general updates if any
        if update_data:
             try:
                 volume.update(update_data, from_public=True) # Assuming update handles persistence
             except Exception as e: # Catch specific errors from update
                 # Log error e
                 return return_api(None, f"Failed updating volume: {e}", 400) # Or appropriate error

        # Fetch updated volume data to return
        updated_volume_info = volume.get_public_keys()
        return return_api(updated_volume_info) # Return updated data


    elif request.method == 'DELETE':
        delete_folder = extract_key(request, 'delete_folder', False)
        try:
             volume.delete(delete_folder=delete_folder) # Handle potential errors
        except (TaskForVolumeRunning, VolumeDownloadedFor) as e:
             # These are expected errors, return specific code
             return return_api(None, e.__class__.__name__, 400)
        except Exception as e:
             # Log error e
             return return_api(None, f"Failed deleting volume: {e}", 500) # Or appropriate error

        return return_api({})


@volumes_api.route('/<int:id>/cover', methods=['GET'])
@error_handler
@auth
def api_volume_cover(id: int):
    # library instance should be accessible or re-instantiated
    cover_data = library.get_volume(id).get_cover() # Raises VolumeNotFound
    return send_file(cover_data, mimetype='image/jpeg'), 200