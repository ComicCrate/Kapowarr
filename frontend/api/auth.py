# -*- coding: utf-8 -*-

from flask import Blueprint, request
from backend.base.logging import LOGGER
from backend.internals.settings import Settings
# Make sure utils are imported correctly (relative import)
from .utils import return_api, error_handler, auth

auth_api = Blueprint('auth_api', __name__)

# The route is now '/' relative to the '/api/auth' prefix
@auth_api.route('/', methods=['POST'])
def api_auth():
    settings = Settings().get_settings()
    ip = request.environ.get('HTTP_X_FORWARDED_FOR', request.remote_addr)

    if settings.auth_password:
        # Use request.get_json(silent=True) to avoid errors on empty/bad body
        data = request.get_json(silent=True) or {}
        given_password = data.get('password') # Safely get password
        if given_password is None:
            # Check if body was empty/invalid JSON before declaring password invalid
            if not request.is_json:
                 return return_api({}, 'InvalidRequestBody', 400)
            return return_api({}, 'PasswordInvalid', 401)


        auth_password = settings.auth_password
        # Ensure auth_password is not None before comparison if it can be unset
        if auth_password is not None and given_password != auth_password:
            LOGGER.warning(f'Login attempt failed from {ip}')
            return return_api({}, 'PasswordInvalid', 401)
        # Handle case where auth_password in settings *is* None/empty?

    LOGGER.info(f'Login attempt successful from {ip}')
    return return_api({'api_key': settings.api_key})


# The route is now '/check' relative to the '/api/auth' prefix
@auth_api.route('/check', methods=['POST'])
@error_handler
@auth
def api_auth_check():
    # This route implicitly checks auth via the @auth decorator
    return return_api({})