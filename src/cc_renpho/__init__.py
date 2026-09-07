"""cc-renpho - download and quality-check a Renpho smart scale history.

Renpho publishes no official API. This reads the same private backend the
Renpho Health app uses, and then tells you what the numbers are actually worth -
most notably which body-composition figures were measured and which were
computed from weight and handed back as though they had been.
"""

__version__ = "0.1.0"

from .client import Renpho, load_credentials
from .errors import ApiError, AuthError, CcRenphoError, ConfigError, IncompleteDownloadError
from .qa import Finding, analyse, run_checks, summarise
from .report import render

__all__ = [
    "Renpho",
    "load_credentials",
    "analyse",
    "run_checks",
    "summarise",
    "Finding",
    "render",
    "CcRenphoError",
    "ConfigError",
    "AuthError",
    "ApiError",
    "IncompleteDownloadError",
    "__version__",
]
