# -*- coding: utf-8 -*-

from flask import Blueprint
from backend.implementations.conversion import preview_mass_convert
from .utils import return_api, error_handler, auth, library # Use relative import

convert_api = Blueprint('convert_api', __name__)

# Note: These endpoints are GET but might be better as POST if they trigger
#       potentially long-running preview operations. Sticking to GET for now.

@convert_api.route('/volumes/<int:id>/convert', methods=['GET'])
@error_handler
@auth
def api_convert_volume(id: int):
    library.get_volume(id) # Check existence
    result = preview_mass_convert(id)
    return return_api(result)


@convert_api.route('/issues/<int:id>/convert', methods=['GET'])
@error_handler
@auth
def api_convert_issue(id: int):
    issue = library.get_issue(id) # Check existence and get issue
    volume_id = issue.get_data().volume_id
    result = preview_mass_convert(volume_id, id)
    return return_api(result)