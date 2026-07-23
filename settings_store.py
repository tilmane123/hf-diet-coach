"""
Persistent storage for user-defined scoring parameter defaults.
Saves/loads per-diet weight overrides to user_settings.json next to this file.
"""

import json
import os
import copy
from config import DIET_WEIGHTS

_SETTINGS_FILE = os.path.join(os.path.dirname(__file__), "user_settings.json")


def load_user_settings() -> dict:
    try:
        with open(_SETTINGS_FILE, "r") as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return {}


def save_user_settings(data: dict):
    with open(_SETTINGS_FILE, "w") as f:
        json.dump(data, f, indent=2)


def get_weights(diet_key: str) -> dict:
    """Return config defaults merged with any saved user overrides for this diet."""
    base = copy.deepcopy(DIET_WEIGHTS[diet_key])
    saved = load_user_settings()
    if diet_key in saved:
        base.update(saved[diet_key])
    return base
