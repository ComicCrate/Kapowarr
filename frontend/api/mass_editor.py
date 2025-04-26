# -*- coding: utf-8 -*-

from flask import Blueprint, request
from typing import Dict, Any, List, Union
from backend.features.mass_edit import run_mass_editor_action
from backend.base.custom_exceptions import InvalidKeyValue, KeyNotFound
from .utils import return_api, error_handler, auth # Use relative import

mass_editor_api = Blueprint('mass_editor_api', __name__)

@mass_editor_api.route('', methods=['POST']) # Changed route base
@error_handler
@auth
def api_mass_editor():
    data = request.get_json()
    if not isinstance(data, dict):
        raise InvalidKeyValue('body', data) # Use specific message

    action: str = data.get('action')
    volume_ids: Union[List[int], Any] = data.get('volume_ids')
    args: Dict[str, Any] = data.get('args', {}) # Default to empty dict

    if not action:
        raise KeyNotFound('action')
    if volume_ids is None: # Check for None specifically
        raise KeyNotFound('volume_ids')

    if not isinstance(action, str):
         raise InvalidKeyValue('action', action) # Ensure action is string
    if not (isinstance(volume_ids, list) and all(isinstance(v, int) for v in volume_ids)):
        raise InvalidKeyValue('volume_ids', volume_ids)
    if not isinstance(args, dict):
        raise InvalidKeyValue('args', args)

    # run_mass_editor_action handles internal validation of action and args
    run_mass_editor_action(action, volume_ids, **args)
    return return_api({})