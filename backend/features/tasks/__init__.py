# -*- coding: utf-8 -*-

"""
Tasks feature package. Exports key components.
"""

# Re-export the main handler and potentially the base Task class
from .handler import TaskHandler, task_library
from .base import Task
from .history import get_task_history, delete_task_history, get_task_planning

# Import all specific task definitions so they can be re-exported
from .definitions import (
    AutoSearchIssue,
    MassRenameIssue,
    MassConvertIssue,
    AutoSearchVolume,
    RefreshAndScanVolume,
    MassRenameVolume,
    MassConvertVolume,
    UpdateAll,
    SearchAll
    # Add any other specific task classes defined in definitions.py here
)

# Define the public interface of the package
__all__ = [
    'TaskHandler',
    'task_library',
    'Task',
    'get_task_history',
    'delete_task_history',
    'get_task_planning',
    # Add all specific task class names here to make them importable
    # via 'from backend.features.tasks import ...'
    'AutoSearchIssue',
    'MassRenameIssue',
    'MassConvertIssue',
    'AutoSearchVolume',
    'RefreshAndScanVolume',
    'MassRenameVolume',
    'MassConvertVolume',
    'UpdateAll',
    'SearchAll',
    # Add any other specific task class names here
]