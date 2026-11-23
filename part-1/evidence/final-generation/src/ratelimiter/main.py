"""ASGI entry point: ``uvicorn ratelimiter.main:app --app-dir src``.

If RATELIMITER_TIERS_FILE is set, tiers are loaded from that JSON file and an invalid file
raises ConfigError, so the service refuses to start. Otherwise the default tiers are used.
"""

import logging
import os

from .app import create_app
from .config import DEFAULT_TIERS, load_tiers_from_json

TIERS_FILE_ENV = "RATELIMITER_TIERS_FILE"

logger = logging.getLogger("ratelimiter")

_tiers_file = os.environ.get(TIERS_FILE_ENV, "")
_tiers = load_tiers_from_json(_tiers_file) if _tiers_file else DEFAULT_TIERS
logger.info(
    "tier source: %s; tiers: %s",
    _tiers_file or "defaults",
    ", ".join(sorted(_tiers)),
)

app = create_app(tiers=_tiers)
