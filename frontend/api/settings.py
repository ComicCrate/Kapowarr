# -*- coding: utf-8 -*-

from flask import Blueprint, request
from backend.implementations.conversion import FileConversionHandler
from backend.internals.settings import Settings
from .utils import return_api, error_handler, auth, extract_key # Use relative import

settings_api = Blueprint('settings_api', __name__)

@settings_api.route('', methods=['GET', 'PUT', 'DELETE']) # Changed route base
@error_handler
@auth
def api_settings():
    settings = Settings()
    if request.method == 'GET':
        result = settings.get_settings().to_dict()
        return return_api(result)

    elif request.method == 'PUT':
        data = request.get_json()
        settings.update(data)
        return return_api(settings.get_settings().to_dict())

    elif request.method == 'DELETE':
        key = extract_key(request, 'key')
        settings.reset(key)
        return return_api(settings.get_settings().to_dict())


@settings_api.route('/api_key', methods=['POST'])
@error_handler
@auth
def api_settings_api_key():
    settings = Settings()
    settings.generate_api_key()
    return return_api(settings.get_settings().to_dict())


@settings_api.route('/availableformats', methods=['GET'])
@error_handler
@auth
def api_settings_available_formats():
    result = list(FileConversionHandler.get_available_formats())
    return return_api(result)