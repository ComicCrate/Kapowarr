# -*- coding: utf-8 -*-

from flask import Blueprint, request
from typing import Union
from backend.implementations.blocklist import (
    add_to_blocklist, delete_blocklist, delete_blocklist_entry,
    get_blocklist, get_blocklist_entry
)
from backend.base.definitions import (
    BlocklistReason, BlocklistReasonID, DownloadSource, GCDownloadSource
)
from backend.base.custom_exceptions import InvalidKeyValue
from .utils import return_api, error_handler, auth, extract_key # Use relative import

blocklist_api = Blueprint('blocklist_api', __name__)

@blocklist_api.route('', methods=['GET', 'POST', 'DELETE']) # Changed route base
@error_handler
@auth
def api_blocklist():
    if request.method == 'GET':
        offset = extract_key(request, 'offset', False)
        blocklist_data = get_blocklist(offset)
        result = [b.as_dict() for b in blocklist_data] # Use as_dict if available
        return return_api(result)

    elif request.method == 'POST':
        data = request.get_json()
        if not isinstance(data, dict):
            raise InvalidKeyValue(value=data)

        # Extract and validate parameters using extract_key where possible
        web_link = extract_key(data, 'web_link') # Required
        web_title = data.get('web_title') # Optional string
        web_sub_title = data.get('web_sub_title') # Optional string
        download_link = data.get('download_link') # Optional string
        source_str = data.get('source') # Optional string
        volume_id = extract_key(data, 'volume_id') # Required int
        issue_id = data.get('issue_id') # Optional int
        reason_id_val = extract_key(data, 'reason_id') # Required BlocklistReasonID

        # Validate optional string types
        if web_title is not None and not isinstance(web_title, str):
             raise InvalidKeyValue('web_title', web_title)
        if web_sub_title is not None and not isinstance(web_sub_title, str):
             raise InvalidKeyValue('web_sub_title', web_sub_title)
        if download_link is not None and not isinstance(download_link, str):
             raise InvalidKeyValue('download_link', download_link)
        if source_str is not None and not isinstance(source_str, str):
             raise InvalidKeyValue('source', source_str)
        if issue_id is not None:
             try:
                 issue_id = int(issue_id)
             except (ValueError, TypeError):
                 raise InvalidKeyValue('issue_id', issue_id)


        # Determine source enum
        source: Union[DownloadSource, GCDownloadSource, None] = None
        if source_str:
             try:
                 # Try matching GCDownloadSource first, then DownloadSource
                 source = GCDownloadSource(source_str)
             except ValueError:
                 try:
                     source = DownloadSource(source_str)
                 except ValueError:
                      # Handle case where source string doesn't match either enum
                      # Option 1: Raise error
                      # raise InvalidKeyValue('source', source_str)
                      # Option 2: Default to None or log a warning
                      source = None


        # Determine reason enum
        try:
            # reason_id_val should already be BlocklistReasonID from extract_key
            reason = BlocklistReason[reason_id_val.name]
        except (KeyError, AttributeError): # Handle potential errors if extract_key failed
            raise InvalidKeyValue('reason_id', data.get('reason_id'))


        result_entry = add_to_blocklist(
            web_link=web_link,
            web_title=web_title,
            web_sub_title=web_sub_title,
            download_link=download_link,
            source=source,
            volume_id=volume_id,
            issue_id=issue_id,
            reason=reason
        )
        return return_api(result_entry.as_dict(), code=201) # Use as_dict

    elif request.method == 'DELETE':
        delete_blocklist()
        return return_api({})


@blocklist_api.route('/<int:id>', methods=['GET', 'DELETE'])
@error_handler
@auth
def api_blocklist_entry(id: int):
    if request.method == 'GET':
        result_entry = get_blocklist_entry(id)
        return return_api(result_entry.as_dict()) # Use as_dict

    elif request.method == 'DELETE':
        delete_blocklist_entry(id)
        return return_api({})