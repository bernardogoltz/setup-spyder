"""Import this package from another repository to open Spyder 5.x."""

from __future__ import annotations

__version__ = "0.3.0"

from .cli import launch, main
from .fork import launch as launch_fork

open_spyder = launch

__all__ = ["__version__", "launch", "launch_fork", "main", "open_spyder"]
