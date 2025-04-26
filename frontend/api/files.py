# -*- coding: utf-8 -*-

from flask import Blueprint, request
from os.path import dirname
from backend.internals.db_models import FilesDB
from backend.base.files import delete_empty_parent_folders, delete_file_folder
from .utils import return_api, error_handler, auth, library # Use relative import

files_api = Blueprint('files_api', __name__)

@files_api.route('/<int:id>', methods=['GET', 'DELETE']) # Changed route base
@error_handler
@auth
def api_files(id: int):
    if request.method == 'GET':
        # fetch raises FileNotFound if not found
        result = FilesDB.fetch(file_id=id)[0] # Assuming fetch returns a list
        return return_api(result)

    elif request.method == 'DELETE':
        # fetch raises FileNotFound if not found
        file_data = FilesDB.fetch(file_id=id)[0]
        filepath = file_data["filepath"]
        volume_id = FilesDB.volume_of_file(filepath)

        delete_file_folder(filepath) # Delete the actual file/folder

        if volume_id:
            # If linked to a volume, try cleaning up empty parent folders
            try:
                volume = library.get_volume(volume_id)
                vf = volume.vd.folder # Get volume folder path
                delete_empty_parent_folders(dirname(filepath), vf)
            except Exception as e:
                 # Log potential errors during cleanup but proceed
                 # from backend.base.logging import LOGGER
                 # LOGGER.warning(f"Error cleaning up parent folders for file {id}: {e}")
                 pass


        FilesDB.delete_file(id) # Delete DB entry
        return return_api({})