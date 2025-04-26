# -*- coding: utf-8 -*-

"""
Base definition for background tasks.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import List, Tuple, Union

class Task(ABC):
    stop: bool
    message: str
    action: str
    display_title: str
    category: str

    @property
    @abstractmethod
    def volume_id(self) -> Union[int, None]:
        ...

    @property
    @abstractmethod
    def issue_id(self) -> Union[int, None]:
        ...

    @abstractmethod
    def __init__(self, **kwargs) -> None:
        ...

    @abstractmethod
    def run(self) -> Union[None, List[Tuple[str, int, Union[int, None]]]]:
        """Run the task

        Returns:
            Union[None, List[Tuple[str, int, Union[int, None]]]]:
            Either `None` if the task has no result or
            `List[Tuple[str, int, Union[int, None]]]` if the task returns
            search results.
        """
        ...