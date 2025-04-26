# -*- coding: utf-8 -*-

from flask import Blueprint, request
from typing import Union

from backend.implementations.root_folders import RootFolders
from backend.base.custom_exceptions import KeyNotFound
from .utils import return_api, error_handler, auth # Use relative import

root_folders_api = Blueprint('root_folders_api', __name__)

@root_folders_api.route('', methods=['GET', 'POST']) # Changed route base
@error_handler
@auth
def api_rootfolder():
    root_folders = RootFolders()

    if request.method == 'GET':
        result = [
            rf.as_dict()
            for rf in root_folders.get_all()
        ]
        return return_api(result)

    elif request.method == 'POST':
        data: dict = request.get_json()
        folder = data.get('folder')
        if folder is None:
            raise KeyNotFound('folder')
        root_folder = root_folders.add(folder).as_dict()
        return return_api(root_folder, code=201)


@root_folders_api.route('/<int:id>', methods=['GET', 'PUT', 'DELETE'])
@error_handler
@auth
def api_rootfolder_id(id: int):
    root_folders = RootFolders()

    if request.method == 'GET':
        root_folder = root_folders.get_one(id).as_dict()
        return return_api(root_folder)

    elif request.method == 'PUT':
        folder: Union[str, None] = request.get_json().get('folder')
        if not folder:
            raise KeyNotFound('folder')
        root_folders[id] = folder # Uses the __setitem__ method
        # Assuming rename doesn't return anything on success for PUT
        # If it returns the updated object, use: return return_api(root_folders.rename(id, folder).as_dict())
        return return_api({})


    elif request.method == 'DELETE':
        root_folders.delete(id)
        return return_api({})