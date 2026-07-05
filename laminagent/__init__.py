"""The Lamin Agent."""

__version__ = "0.1.0"

from ._lag import lamin_executable_lag
from ._setup import setup

lag = lamin_executable_lag

__all__ = ["lamin_executable_lag", "lag", "setup"]
