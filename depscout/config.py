import json
import os
import pathlib

CONFIG_FILE = pathlib.Path.home() / ".config" / "depscout" / "config.json"


def get(key):
    try:
        with open(CONFIG_FILE) as f:
            return json.load(f).get(key)
    except Exception:
        return None


def set(key, value):
    CONFIG_FILE.parent.mkdir(parents=True, exist_ok=True)
    data = {}
    try:
        with open(CONFIG_FILE) as f:
            data = json.load(f)
    except Exception:
        pass
    data[key] = value
    with open(CONFIG_FILE, "w") as f:
        json.dump(data, f, indent=2)
