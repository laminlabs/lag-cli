"""The Lamin Agent."""

__version__ = "0.1.0"

from ._lag import lamin_executable_lag as lag
from ._setup import setup

__all__ = ["lag", "setup"]
