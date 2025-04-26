# -*- coding: utf-8 -*-

from flask import Blueprint, request
from typing import Dict, Any
from backend.features.download_queue import (
    DownloadHandler, delete_download_history, get_download_history
)
from backend.base.custom_exceptions import InvalidKeyValue
from .utils import return_api, error_handler, auth, extract_key # Use relative import

activity_api = Blueprint('activity_api', __name__)

@activity_api.route('/queue', methods=['GET', 'DELETE'])
@error_handler
@auth
def api_downloads():
    download_handler = DownloadHandler()

    if request.method == 'GET':
        result = download_handler.get_all()
        return return_api(result)

    elif request.method == 'DELETE':
        download_handler.remove_all()
        return return_api({})


@activity_api.route('/queue/<int:download_id>', methods=['GET', 'PUT', 'DELETE'])
@error_handler
@auth
def api_delete_download(download_id: int):
    download_handler = DownloadHandler()

    if request.method == 'GET':
        result = download_handler.get_one(download_id).todict()
        return return_api(result)

    elif request.method == 'PUT':
        index: int = extract_key(request, 'index')
        download_handler.set_queue_location(download_id, index)
        return return_api({})

    elif request.method == 'DELETE':
        # Use get_json with silent=True to handle cases where no body is sent
        data: Dict[str, Any] = request.get_json(silent=True) or {}
        blocklist = data.get('blocklist', False) # Default to False if not provided
        if not isinstance(blocklist, bool):
             raise InvalidKeyValue('blocklist', blocklist)

        download_handler.remove(download_id, blocklist)
        return return_api({})


@activity_api.route('/history', methods=['GET', 'DELETE'])
@error_handler
@auth
def api_download_history():
    if request.method == 'GET':
        volume_id: int = extract_key(request, 'volume_id', False)
        issue_id: int = extract_key(request, 'issue_id', False)
        offset: int = extract_key(request, 'offset', False)
        result = get_download_history(volume_id, issue_id, offset)
        return return_api(result)

    elif request.method == 'DELETE':
        delete_download_history()
        return return_api({})


@activity_api.route('/folder', methods=['DELETE'])
@error_handler
@auth
def api_empty_download_folder():
    DownloadHandler().empty_download_folder()
    return return_api({})