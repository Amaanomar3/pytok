from __future__ import annotations

import logging
from urllib.parse import urlencode
from typing import TYPE_CHECKING, Iterator, Optional

from .video import Video
from .sound import Sound
from .user import User
from .hashtag import Hashtag

if TYPE_CHECKING:
    from ..tiktok import PyTok


class Trending:
    """Contains static methods related to trending."""

    parent: PyTok
    
    def __init__(self, parent: Optional['PyTok'] = None):
        """Initialize with parent instance"""
        self.parent = parent
        
        # Make sure parent is set
        if not hasattr(self, 'parent') or self.parent is None:
            from inspect import currentframe
            frame = currentframe()
            if frame and frame.f_back and 'self' in frame.f_back.f_locals:
                # Try to get parent from caller
                caller = frame.f_back.f_locals['self']
                if hasattr(caller, 'parent'):
                    self.parent = caller.parent
            del frame  # Avoid reference cycles

    @staticmethod
    def videos(count=30, **kwargs) -> Iterator[Video]:
        """
        Returns Videos that are trending on TikTok.

        - Parameters:
            - count (int): The amount of videos you want returned.
        """

        raise NotImplementedError()
