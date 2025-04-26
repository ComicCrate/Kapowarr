# -*- coding: utf-8 -*-

from flask import Blueprint, request
from backend.features.library_import import (
    import_library, propose_library_import
)
from backend.base.custom_exceptions import InvalidKeyValue
from .utils import return_api, error_handler, auth, extract_key # Use relative import

library_import_api = Blueprint('library_import_api', __name__)

@library_import_api.route('', methods=['GET', 'POST']) # Changed route base
@error_handler
@auth
def api_library_import():
    if request.method == 'GET':
        folder_filter = extract_key(request, 'folder_filter', check_existence=False)
        limit = extract_key(request, 'limit', check_existence=False)
        only_english = extract_key(request, 'only_english', check_existence=False)
        limit_parent_folder = extract_key(request, 'limit_parent_folder', check_existence=False)
        result = propose_library_import(
            folder_filter, limit, limit_parent_folder, only_english
        )
        return return_api(result)

    elif request.method == 'POST':
        data = request.get_json()
        rename_files = extract_key(request, 'rename_files', False)

        if not isinstance(data, list) or not all(
            isinstance(e, dict) and 'filepath' in e and 'id' in e for e in data
        ):
            raise InvalidKeyValue(value=data) # No key specified, raise with value

        import_library(data, rename_files)
        return return_api({}, code=201)