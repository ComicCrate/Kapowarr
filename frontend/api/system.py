# -*- coding: utf-8 -*-

from flask import Blueprint, request, send_file
from io import BytesIO, StringIO
from os.path import exists
from datetime import datetime
from typing import Union, Type

from backend.base.logging import LOGGER, get_log_filepath
from backend.base.custom_exceptions import (
    LogFileNotFound, TaskNotFound, InvalidKeyValue
)
from backend.features.tasks import (
    Task, TaskHandler, delete_task_history, get_task_history,
    get_task_planning, task_library
)
from backend.internals.server import SERVER
from backend.internals.settings import about_data
from .utils import return_api, error_handler, auth, extract_key # Use relative import

system_api = Blueprint('system_api', __name__)

@system_api.route('/about', methods=['GET'])
@error_handler
@auth
def api_about():
    return return_api(about_data)


@system_api.route('/logs', methods=['GET'])
@error_handler
@auth
def api_logs():
    file = get_log_filepath()
    if not exists(file):
        raise LogFileNotFound

    sio = StringIO()
    for ext in ('.1', ''):
        lf = file + ext
        if not exists(lf):
            continue
        with open(lf, 'r', encoding='utf-8') as f: # Specify encoding
            sio.writelines(f)

    return send_file(
        BytesIO(sio.getvalue().encode('utf-8')),
        mimetype="application/octet-stream",
        download_name=f'Kapowarr_log_{datetime.now().strftime("%Y_%m_%d_%H_%M")}.txt'
    ), 200


@system_api.route('/tasks', methods=['GET', 'POST'])
@error_handler
@auth
def api_tasks():
    task_handler = TaskHandler()

    if request.method == 'GET':
        tasks = task_handler.get_all()
        return return_api(tasks)

    elif request.method == 'POST':
        data = request.get_json()
        if not isinstance(data, dict):
            raise InvalidKeyValue(value=data)

        task_cmd = data.get('cmd', '')
        task_class: Union[Type[Task], None] = task_library.get(task_cmd)
        if not task_class:
             raise TaskNotFound(f"Task command '{task_cmd}' not found") # Add detail

        # --- Refactored Argument Handling ---
        kwargs = {}
        required_args = {}
        optional_args = {}

        # Define argument requirements per task action dynamically if possible,
        # or use a mapping like this:
        task_arg_config = {
            'refresh_and_scan': {'required': ['volume_id']},
            'auto_search': {'required': ['volume_id']},
            'auto_search_issue': {'required': ['volume_id', 'issue_id']},
            'mass_rename': {'required': ['volume_id'], 'optional': ['filepath_filter']},
            'mass_rename_issue': {'required': ['volume_id', 'issue_id'], 'optional': ['filepath_filter']},
            'mass_convert': {'required': ['volume_id'], 'optional': ['filepath_filter']},
            'mass_convert_issue': {'required': ['volume_id', 'issue_id'], 'optional': ['filepath_filter']},
            'update_all': {'optional': ['allow_skipping']}
            # Add other tasks here
        }

        config = task_arg_config.get(task_class.action, {})
        required_args = config.get('required', [])
        optional_args = config.get('optional', [])

        # Validate required arguments
        for arg_name in required_args:
            arg_value = data.get(arg_name)
            if arg_value is None:
                 raise InvalidKeyValue(f"Missing required argument '{arg_name}' for task '{task_cmd}'", arg_value)
             # Add specific type checks if needed (e.g., isinstance(arg_value, int))
            if arg_name in ('volume_id', 'issue_id') and not isinstance(arg_value, int):
                 raise InvalidKeyValue(f"Argument '{arg_name}' must be an integer", arg_value)
            kwargs[arg_name] = arg_value

        # Process optional arguments
        for arg_name in optional_args:
            arg_value = data.get(arg_name)
            if arg_name == 'filepath_filter':
                 if arg_value is not None and not isinstance(arg_value, list):
                     raise InvalidKeyValue(arg_name, arg_value)
                 kwargs[arg_name] = arg_value or [] # Default to empty list if None
            elif arg_name == 'allow_skipping':
                 if arg_value is not None and not isinstance(arg_value, bool):
                      raise InvalidKeyValue(arg_name, arg_value)
                 kwargs[arg_name] = arg_value if arg_value is not None else False # Default to False
            # Handle other optional args
            else:
                 kwargs[arg_name] = arg_value

        # --- End Refactored Argument Handling ---

        task_instance = task_class(**kwargs)
        result = task_handler.add(task_instance)
        return return_api({'id': result}, code=201)


@system_api.route('/tasks/history', methods=['GET', 'DELETE'])
@error_handler
@auth
def api_task_history():
    if request.method == 'GET':
        offset = extract_key(request, 'offset', False)
        tasks = get_task_history(offset)
        return return_api(tasks)

    elif request.method == 'DELETE':
        delete_task_history()
        return return_api({})


@system_api.route('/tasks/planning', methods=['GET'])
@error_handler
@auth
def api_task_planning():
    result = get_task_planning()
    return return_api(result)


@system_api.route('/tasks/<int:task_id>', methods=['GET', 'DELETE'])
@error_handler
@auth
def api_task(task_id: int):
    task_handler = TaskHandler()

    if request.method == 'GET':
        task = task_handler.get_one(task_id)
        return return_api(task)

    elif request.method == 'DELETE':
        task_handler.remove(task_id)
        return return_api({})


@system_api.route('/power/shutdown', methods=['POST'])
@error_handler
@auth
def api_shutdown():
    SERVER.shutdown()
    return return_api({})


@system_api.route('/power/restart', methods=['POST'])
@error_handler
@auth
def api_restart():
    SERVER.restart()
    return return_api({})