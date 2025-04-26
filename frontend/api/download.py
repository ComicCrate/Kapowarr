# -*- coding: utf-8 -*-

from flask import Blueprint, request
from asyncio import run

from backend.features.download_queue import DownloadHandler
from backend.features.search import manual_search
from backend.base.definitions import FailReason
from .utils import return_api, error_handler, auth, extract_key, library # Use relative import

download_api = Blueprint('download_api', __name__)

@download_api.route('/volumes/<int:id>/manualsearch', methods=['GET'])
@error_handler
@auth
def api_volume_manual_search(id: int):
    library.get_volume(id) # Check existence
    result = manual_search(id) # Assuming manual_search is synchronous
    return return_api(result)


@download_api.route('/volumes/<int:id>/download', methods=['POST'])
@error_handler
@auth
def api_volume_download(id: int):
    library.get_volume(id) # Check existence
    link: str = extract_key(request, 'link')
    force_match: bool = extract_key(request, 'force_match', False) # Default False
    # Assuming DownloadHandler().add is async
    added_downloads, fail_reason = run(DownloadHandler().add(link, id, force_match=force_match))
    return return_api(
        {
            'result': added_downloads, # Return the list of download dicts
            'fail_reason': fail_reason.value if isinstance(fail_reason, FailReason) else None # Convert enum
        },
        code=201 if added_downloads else 400 # Adjust code based on success
    )


@download_api.route('/issues/<int:id>/manualsearch', methods=['GET'])
@error_handler
@auth
def api_issue_manual_search(id: int):
    issue = library.get_issue(id) # Check existence
    volume_id = issue.get_data().volume_id
    result = manual_search(volume_id, id) # Assuming manual_search is synchronous
    return return_api(result)


@download_api.route('/issues/<int:id>/download', methods=['POST'])
@error_handler
@auth
def api_issue_download(id: int):
    issue = library.get_issue(id) # Check existence
    volume_id = issue.get_data().volume_id
    link = extract_key(request, 'link')
    force_match: bool = extract_key(request, 'force_match', False) # Default False
    # Assuming DownloadHandler().add is async
    added_downloads, fail_reason = run(DownloadHandler().add(link, volume_id, id, force_match=force_match))
    return return_api(
        {
            'result': added_downloads, # Return the list of download dicts
            'fail_reason': fail_reason.value if isinstance(fail_reason, FailReason) else None # Convert enum
        },
        code=201 if added_downloads else 400 # Adjust code based on success
    )