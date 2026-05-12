# utils/model_store.py — Persist trained ML models to disk so they survive restarts
from __future__ import annotations
import logging
import os
import pickle

logger = logging.getLogger(__name__)

_HERE       = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_MODELS_DIR = os.path.join(_HERE, "model_cache")
os.makedirs(_MODELS_DIR, exist_ok=True)


def _path(name: str) -> str:
    return os.path.join(_MODELS_DIR, f"{name}.pkl")


def save_model(name: str, obj) -> bool:
    """Pickle a model object to disk. Returns True on success."""
    try:
        with open(_path(name), "wb") as f:
            pickle.dump(obj, f)
        logger.info("Model '%s' saved to disk.", name)
        return True
    except Exception as e:
        logger.error("save_model '%s' failed: %s", name, e)
        return False


def load_model(name: str):
    """Load a pickled model from disk. Returns None if not found."""
    p = _path(name)
    if not os.path.exists(p):
        return None
    try:
        with open(p, "rb") as f:
            obj = pickle.load(f)
        logger.info("Model '%s' loaded from disk.", name)
        return obj
    except Exception as e:
        logger.error("load_model '%s' failed: %s", name, e)
        return None


def model_exists(name: str) -> bool:
    return os.path.exists(_path(name))


def delete_model(name: str) -> None:
    p = _path(name)
    if os.path.exists(p):
        os.remove(p)
