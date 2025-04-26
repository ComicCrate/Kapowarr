#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from argparse import ArgumentParser
from multiprocessing import set_start_method
from os import environ
from typing import NoReturn, Union

# Keep necessary imports
from backend.base.definitions import RestartVersion
from backend.base.helpers import check_python_version
from backend.base.logging import LOGGER, setup_logging
from backend.features.download_queue import DownloadHandler
from backend.features.tasks import TaskHandler
from backend.implementations.flaresolverr import FlareSolverr
from backend.internals.db import close_all_db, set_db_location, setup_db
from backend.internals.server import SERVER, handle_restart_version
from backend.internals.settings import Settings

# Import the new process manager function
from backend.internals.process_manager import run_sub_process

def _main(
    restart_version: RestartVersion,
    db_folder: Union[str, None] = None
) -> NoReturn:
    """The main function of the Kapowarr application process."""
    # set_start_method('spawn') # Might only be needed in the main guard block
    setup_logging()
    LOGGER.info('Starting up Kapowarr process')

    if not check_python_version():
        exit(1) # Exit if Python version is insufficient

    try:
        set_db_location(db_folder)
    except ValueError as e:
         # Handle specific DB location error gracefully
         LOGGER.error(f"Database setup error: {e}")
         exit(1)

    SERVER.create_app() # Create the Flask app instance

    download_handler = None
    task_handler = None
    flaresolverr = None

    try:
        with SERVER.app.app_context():
            LOGGER.debug("Application context acquired.")
            handle_restart_version(restart_version)
            LOGGER.debug("Setting up database...")
            setup_db() # Setup database schema and migrations
            LOGGER.debug("Database setup complete.")

            settings = Settings().get_settings() # Load settings
            LOGGER.debug("Settings loaded.")
            flaresolverr = FlareSolverr() # Initialize FlareSolverr
            SERVER.set_url_base(settings.url_base) # Set Flask URL base
            LOGGER.debug(f"URL base set to: {settings.url_base}")

            if settings.flaresolverr_base_url:
                LOGGER.info(f"Attempting to enable FlareSolverr at {settings.flaresolverr_base_url}")
                if flaresolverr.enable_flaresolverr(settings.flaresolverr_base_url):
                     LOGGER.info("FlareSolverr enabled successfully.")
                else:
                     LOGGER.warning("Failed to enable FlareSolverr.")

            LOGGER.debug("Initializing DownloadHandler...")
            download_handler = DownloadHandler()
            # Run load_downloads in a separate thread managed by the server instance
            load_thread = SERVER.get_db_thread(
                 target=download_handler.load_downloads,
                 name="Download Importer"
            )
            load_thread.start()
            # download_handler.load_downloads() # Consider if this needs to block or run async

            LOGGER.debug("Initializing TaskHandler...")
            task_handler = TaskHandler()
            task_handler.handle_intervals() # Start interval checks
            LOGGER.debug("TaskHandler initialized.")

        # Run the web server (outside the initial app_context)
        LOGGER.info("Starting web server...")
        SERVER.run(settings.host, settings.port)
        # Server run blocks here until shutdown/restart

    except Exception as e:
         LOGGER.exception("An unexpected error occurred during Kapowarr execution:")
         # Perform essential cleanup even on error before exiting
         if download_handler: download_handler.stop_handle()
         if task_handler: task_handler.stop_handle()
         if flaresolverr and flaresolverr.is_enabled(): flaresolverr.disable_flaresolverr()
         close_all_db()
         exit(1) # Exit with error code

    finally:
        LOGGER.info("Performing final cleanup...")
        # Ensure handlers are stopped and DB is closed on normal exit/shutdown
        if download_handler: download_handler.stop_handle()
        if task_handler: task_handler.stop_handle()
        if flaresolverr and flaresolverr.is_enabled(): flaresolverr.disable_flaresolverr()
        close_all_db()
        LOGGER.info("Cleanup complete.")

        if SERVER.restart_version is not None:
            LOGGER.info(f'Exiting process to restart (Version: {SERVER.restart_version.value})...')
            exit(SERVER.restart_version.value)
        else:
            LOGGER.info('Exiting process normally...')
            exit(0)


# Removed _run_sub_process and _stop_sub_process functions


def Kapowarr() -> int:
    """The main function of Kapowarr, manages the sub-process."""
    rc = RestartVersion.NORMAL.value
    while rc >= RestartVersion.NORMAL.value: # Check if it's a valid restart code
        LOGGER.info(f"Kapowarr manager: Starting/Restarting process (Restart code: {rc})")
        try:
             restart_enum = RestartVersion(rc)
        except ValueError:
             LOGGER.warning(f"Invalid restart code {rc}, stopping.")
             break # Exit loop if invalid code
        rc = run_sub_process(restart_enum)
        LOGGER.info(f"Kapowarr manager: Process exited with code {rc}")
        # Loop continues if rc is a valid RestartVersion value >= 131

    LOGGER.info("Kapowarr manager: Exiting.")
    return rc if rc < RestartVersion.NORMAL.value else 0 # Return actual exit code or 0


if __name__ == "__main__":
    if environ.get("KAPOWARR_RUN_MAIN") == "1":
        # This block runs inside the sub-process
        set_start_method('spawn', force=True) # Set start method for child processes if needed

        parser = ArgumentParser(
            description="Kapowarr: A comic book library manager."
        )
        parser.add_argument(
            '-d', '--DatabaseFolder',
            type=str,
            help="Folder for the Kapowarr database file."
        )
        args = parser.parse_args()
        db_folder = args.DatabaseFolder

        try:
            # Get restart version from environment
            rv_value = int(environ.get("KAPOWARR_RESTART_VERSION", RestartVersion.NORMAL.value))
            rv = RestartVersion(rv_value)
        except ValueError:
            # Default to NORMAL if the value is invalid
            rv = RestartVersion.NORMAL

        # Execute the main application logic within the sub-process
        _main(
            restart_version=rv,
            db_folder=db_folder
        )
        # _main calls exit() internally

    else:
        # This block runs in the initial process, managing the sub-process
        rc = Kapowarr()
        exit(rc)