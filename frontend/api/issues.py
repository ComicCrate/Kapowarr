# -*- coding: utf-8 -*-

from flask import Blueprint, request
from backend.base.custom_exceptions import InvalidKeyValue
from .utils import return_api, error_handler, auth, library # Use relative import

issues_api = Blueprint('issues_api', __name__)

@issues_api.route('/<int:id>', methods=['GET', 'PUT']) # Changed route base
@error_handler
@auth
def api_issues(id: int):
    issue = library.get_issue(id) # Raises IssueNotFound

    if request.method == 'GET':
        result = issue.get_data().as_dict() # Use as_dict() if available
        return return_api(result)

    elif request.method == 'PUT':
        edit_info: dict = request.get_json()
        update_data = {}

        if 'monitored' in edit_info:
             monitored_val = edit_info['monitored']
             if not isinstance(monitored_val, bool):
                  raise InvalidKeyValue('monitored', monitored_val)
             update_data['monitored'] = monitored_val

        # Add other editable fields for issues here with validation

        if update_data:
             try:
                 issue.update(update_data) # Assuming update handles persistence
             except Exception as e: # Catch specific errors from update
                 # Log error e
                 return return_api(None, f"Failed updating issue: {e}", 400) # Or appropriate error


        result = issue.get_data().as_dict() # Return updated data
        return return_api(result)