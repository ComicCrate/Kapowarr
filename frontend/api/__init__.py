# -*- coding: utf-8 -*-

from flask import Blueprint

# Import blueprint instances from the new modules
# Use relative imports since they are in the same package
from .auth import auth_api
from .system import system_api
from .settings import settings_api
from .root_folders import root_folders_api
from .library_import import library_import_api
from .volumes import volumes_api
from .issues import issues_api
from .rename import rename_api
from .convert import convert_api
from .download import download_api
from .activity import activity_api
from .blocklist import blocklist_api
from .credentials import credentials_api
from .external_clients import external_clients_api
from .mass_editor import mass_editor_api
from .files import files_api

# Main API blueprint that aggregates others
api = Blueprint('api', __name__)

# Register individual blueprints with URL prefixes
# (Adjust prefixes as needed or register directly to the main 'api' blueprint without prefix)
api.register_blueprint(auth_api, url_prefix='/auth')
api.register_blueprint(system_api, url_prefix='/system')
api.register_blueprint(settings_api, url_prefix='/settings')
api.register_blueprint(root_folders_api, url_prefix='/rootfolder')
api.register_blueprint(library_import_api, url_prefix='/libraryimport')
api.register_blueprint(volumes_api, url_prefix='/volumes')
api.register_blueprint(issues_api, url_prefix='/issues')
api.register_blueprint(rename_api) # Registering without prefix assumes routes like /volumes/<id>/rename
api.register_blueprint(convert_api) # Registering without prefix assumes routes like /volumes/<id>/convert
api.register_blueprint(download_api) # Registering without prefix assumes routes like /volumes/<id>/download
api.register_blueprint(activity_api, url_prefix='/activity')
api.register_blueprint(blocklist_api, url_prefix='/blocklist')
api.register_blueprint(credentials_api, url_prefix='/credentials')
api.register_blueprint(external_clients_api, url_prefix='/externalclients')
api.register_blueprint(mass_editor_api, url_prefix='/masseditor')
api.register_blueprint(files_api, url_prefix='/files')