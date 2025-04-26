# backend/internals/process_manager.py
# -*- coding: utf-8 -*-

"""
Handles running Kapowarr as a sub-process for restarts.
"""

from os import environ, name, path as os_path # Use alias to avoid conflict
from signal import SIGINT, SIGTERM, signal
from subprocess import Popen # Remove subprocess import if not used elsewhere
from sys import argv
from atexit import register
from typing import NoReturn # Keep NoReturn if needed elsewhere, otherwise remove

from backend.base.definitions import Constants, RestartVersion
from backend.base.helpers import get_python_exe
from backend.base.logging import LOGGER


def _stop_sub_process(proc: Popen) -> None:
    """Gracefully stop the sub-process unless that fails. Then terminate it."""
    if proc.poll() is not None: # Use poll() for non-blocking check
        return

    LOGGER.info("Attempting to gracefully stop sub-process...")
    try:
        if name != 'nt':
            # Send SIGINT on POSIX systems
            proc.send_signal(SIGINT)
        else:
            # Use GenerateConsoleCtrlEvent on Windows
            import win32api  # type: ignore
            import win32con  # type: ignore
            # Ensure proc.pid is valid before calling
            if proc.pid is not None:
                win32api.GenerateConsoleCtrlEvent(win32con.CTRL_C_EVENT, proc.pid)

        # Wait for a short period for graceful shutdown
        proc.wait(timeout=Constants.SUB_PROCESS_TIMEOUT / 2) # Wait half the timeout
        LOGGER.info("Sub-process stopped gracefully.")

    except ProcessLookupError:
        LOGGER.info("Sub-process already terminated.")
    # Catch specific exceptions if possible, e.g., TimeoutExpired
    except Exception as e:
        LOGGER.warning(f"Graceful shutdown failed ({e}), terminating sub-process.")
        proc.terminate() # Force terminate if graceful shutdown fails or times out
        try:
            proc.wait(timeout=Constants.SUB_PROCESS_TIMEOUT / 2) # Wait for termination
        except Exception as term_e: # Catch specific exception like TimeoutExpired
            LOGGER.error(f"Failed to terminate sub-process: {term_e}")


def run_sub_process(
    restart_version: RestartVersion = RestartVersion.NORMAL
) -> int:
    """Start the sub-process that Kapowarr will be run in."""
    env = {
        **environ,
        "KAPOWARR_RUN_MAIN": "1",
        "KAPOWARR_RESTART_VERSION": str(restart_version.value),
        "PYTHONUNBUFFERED": "1"
    }

    # Get the absolute path to Kapowarr.py relative to *this* file
    # (process_manager.py)
    current_dir = os_path.dirname(os_path.abspath(__file__))
    kapowarr_script_path = os_path.abspath(os_path.join(current_dir, '..', '..', 'Kapowarr.py'))

    if not os_path.exists(kapowarr_script_path):
        LOGGER.error(f"Kapowarr.py script not found at expected location: {kapowarr_script_path}")
        return 1 # Indicate an error

    comm = [get_python_exe(), "-u", kapowarr_script_path] + argv[1:]
    LOGGER.info(f"Starting sub-process with command: {' '.join(comm)}")

    # --- Removed creationflags ---
    # creationflags = 0
    # if name == 'nt':
    #     import subprocess
    #     creationflags = subprocess.CREATE_NO_WINDOW
    # --- End Removal ---

    try:
        proc = Popen(
            comm,
            env=env,
            # creationflags=creationflags # Removed this line
            # Let stdout and stderr inherit from parent by default
            stdout=None,
            stderr=None,
        )
    except Exception as popen_error:
        LOGGER.error(f"Failed to start sub-process: {popen_error}")
        return 1 # Indicate error

    # Register a function to stop the subprocess on main process exit
    # Ensure proc is defined before registering
    if 'proc' in locals():
        register(_stop_sub_process, proc=proc)
        # Handle SIGTERM to also attempt graceful shutdown
        signal(SIGTERM, lambda signal_no, frame: _stop_sub_process(proc))
    else:
        # Handle case where Popen failed immediately
        return 1

    try:
        return_code = proc.wait()
        LOGGER.info(f"Sub-process exited with code: {return_code}")
        return return_code
    except (KeyboardInterrupt, SystemExit):
        LOGGER.info("Main process interrupted, stopping sub-process.")
        _stop_sub_process(proc)
        return 0 # Treat interrupt as normal shutdown
    except Exception as e:
        LOGGER.error(f"Error waiting for sub-process: {e}")
        _stop_sub_process(proc)
        return 1 # Indicate an error