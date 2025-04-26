# -*- coding: utf-8 -*-

from flask import Blueprint
from backend.implementations.naming import preview_mass_rename
from .utils import return_api, error_handler, auth, library # Use relative import

rename_api = Blueprint('rename_api', __name__)

# Note: These endpoints are GET but might be better as POST if they trigger
#       potentially long-running preview operations. Sticking to GET for now.

@rename_api.route('/volumes/<int:id>/rename', methods=['GET'])
@error_handler
@auth
def api_rename_volume(id: int):
    library.get_volume(id) # Check existence
    # Assuming preview_mass_rename returns a tuple (result, maybe_folder)
    result, _ = preview_mass_rename(id)
    return return_api(result)


@rename_api.route('/issues/<int:id>/rename', methods=['GET'])
@error_handler
@auth
def api_rename_issue(id: int):
    issue = library.get_issue(id) # Check existence and get issue
    volume_id = issue.get_data().volume_id
    # Assuming preview_mass_rename returns a tuple (result, maybe_folder)
    result, _ = preview_mass_rename(volume_id, id)
    return return_api(result)