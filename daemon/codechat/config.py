# codechat/config.py
import json
import os
from typing import Any

import structlog
logger = structlog.get_logger(__name__)

_cfg: dict[str, Any] = {}

def get_config() -> dict[str, Any]:
    return _cfg

def set_config() -> None:
    global _cfg
    cfg_path = os.path.expanduser("/config/config.json")
    if os.path.exists(cfg_path):
        _cfg = json.load(open(cfg_path))
    else:
        logger.warning("No config file found at /config/config.json")
