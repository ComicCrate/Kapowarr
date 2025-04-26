# -*- coding: utf-8 -*-

from flask import Blueprint, request
from backend.implementations.credentials import Credentials
from backend.base.definitions import CredentialData, CredentialSource
from backend.base.custom_exceptions import InvalidKeyValue, KeyNotFound
from .utils import return_api, error_handler, auth # Use relative import

credentials_api = Blueprint('credentials_api', __name__)

@credentials_api.route('', methods=['GET', 'POST']) # Changed route base
@error_handler
@auth
def api_credentials():
    cred = Credentials()

    if request.method == 'GET':
        result = [c.as_dict() for c in cred.get_all()] # Use as_dict
        return return_api(result)

    elif request.method == 'POST':
        data = request.get_json()
        if not isinstance(data, dict):
            raise InvalidKeyValue(value=data)

        source_str = data.get('source')
        if not source_str:
            raise KeyNotFound('source')

        try:
            source = CredentialSource(source_str)
        except ValueError:
            raise InvalidKeyValue('source', source_str)

        # Create CredentialData object, ID will be assigned by add method
        cred_data = CredentialData(
            id=-1, # Placeholder ID
            source=source,
            username=data.get("username"),
            email=data.get("email"),
            password=data.get("password"),
            api_key=data.get("api_key")
        )

        result_cred = cred.add(cred_data) # add method handles validation
        return return_api(result_cred.as_dict(), code=201) # Use as_dict


@credentials_api.route('/<int:id>', methods=['GET', 'DELETE'])
@error_handler
@auth
def api_credential(id: int):
    cred = Credentials()
    if request.method == 'GET':
        result_cred = cred.get_one(id)
        return return_api(result_cred.as_dict()) # Use as_dict

    elif request.method == 'DELETE':
        cred.delete(id)
        return return_api({})