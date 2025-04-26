# -*- coding: utf-8 -*-

from flask import Blueprint, request
from backend.implementations.external_clients import ExternalClients
from backend.base.custom_exceptions import InvalidKeyValue # Import specific exceptions if needed
from .utils import return_api, error_handler, auth # Use relative import

external_clients_api = Blueprint('external_clients_api', __name__)

@external_clients_api.route('', methods=['GET', 'POST']) # Changed route base
@error_handler
@auth
def api_external_clients():
    if request.method == 'GET':
        result = ExternalClients.get_clients()
        return return_api(result)

    elif request.method == 'POST':
        data: dict = request.get_json()
        # Extract necessary keys, perform validation if needed
        client_data = {
            k: data.get(k)
            for k in ('client_type', 'title', 'base_url', 'username', 'password', 'api_token')
        }
        # Add method performs validation internally
        new_client = ExternalClients.add(**client_data)
        return return_api(new_client.get_client_data(), code=201)


@external_clients_api.route('/options', methods=['GET'])
@error_handler
@auth
def api_external_clients_keys():
    # Consider adding error handling if get_client_types can fail
    result = {
        k: v.required_tokens
        for k, v in ExternalClients.get_client_types().items()
    }
    return return_api(result)


@external_clients_api.route('/test', methods=['POST'])
@error_handler
@auth
def api_external_clients_test():
    data: dict = request.get_json()
    # Extract necessary keys
    test_data = {
        k: data.get(k)
        for k in ('client_type', 'base_url', 'username', 'password', 'api_token')
    }
    # test method performs validation internally
    result = ExternalClients.test(**test_data)
    return return_api(result)


@external_clients_api.route('/<int:id>', methods=['GET', 'PUT', 'DELETE'])
@error_handler
@auth
def api_external_client(id: int):
    # get_client raises ExternalClientNotFound if ID is invalid
    client = ExternalClients.get_client(id)

    if request.method == 'GET':
        result = client.get_client_data()
        return return_api(result)

    elif request.method == 'PUT':
        data: dict = request.get_json()
        # Extract necessary keys
        update_data = {
            k: data.get(k)
            for k in ('title', 'base_url', 'username', 'password', 'api_token')
        }
        # update_client performs validation internally
        client.update_client(update_data)
        # Return updated data
        return return_api(client.get_client_data())


    elif request.method == 'DELETE':
        # delete_client performs validation internally (e.g., ClientDownloading)
        client.delete_client()
        return return_api({})