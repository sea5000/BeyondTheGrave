import json
import os
import shutil
import threading
import uuid
from datetime import datetime, timezone

DATA_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data", "sessions")
_lock = threading.Lock()


def _now():
    return datetime.now(timezone.utc).isoformat()


def _rel(profile, path):
    return os.path.relpath(path, profile["dir"])


def _abs(profile, rel):
    return os.path.join(profile["dir"], rel)


def _coverage_defaults():
    return {c: 0.0 for c in _CATEGORIES}


_CATEGORIES = [
    "identity",
    "family",
    "friends",
    "romance",
    "career",
    "life_events",
    "values",
    "favorites",
    "personality",
    "speech_style",
    "wisdom",
    "phrases",
]


def create_session(name, model):
    sid = uuid.uuid4().hex[:12]
    sdir = os.path.join(DATA_DIR, sid)
    os.makedirs(os.path.join(sdir, "voice"), exist_ok=True)
    os.makedirs(os.path.join(sdir, "generated"), exist_ok=True)
    profile = {
        "id": sid,
        "dir": sdir,
        "created": _now(),
        "name": name.strip() or "Anonymous",
        "model": model,
        "phase": "setup",
        "topics_coverage": _coverage_defaults(),
        "facts": [],
        "transcript": [],
        "voice_ref": None,
        "phrases": [],
        "dossier": None,
        "phrase_prompts": [],
        "turns": 0,
    }
    save_profile(profile)
    return profile


def _profile_path(sid):
    return os.path.join(DATA_DIR, sid, "profile.json")


def _read_profile(sid):
    path = _profile_path(sid)
    if not os.path.exists(path):
        return None
    with open(path) as f:
        return json.load(f)


def load_profile(sid):
    p = _read_profile(sid)
    if p is None:
        return None
    p["dir"] = os.path.join(DATA_DIR, sid)
    if "topics_coverage" not in p:
        p["topics_coverage"] = _coverage_defaults()
    return p


def save_profile(profile):
    profile["updated"] = _now()
    with _lock:
        os.makedirs(profile["dir"], exist_ok=True)
        # strip the absolute dir before persisting (restored on load); never mutate caller's dict
        saved = dict(profile)
        saved.pop("dir", None)
        tmp = _profile_path(profile["id"]) + ".tmp"
        with open(tmp, "w") as f:
            json.dump(saved, f, indent=2, default=str)
        os.replace(tmp, _profile_path(profile["id"]))


def add_transcript(profile, role, content):
    profile.setdefault("transcript", []).append({"role": role, "content": content, "ts": _now()})
    save_profile(profile)


def session_abs_path(profile, *parts):
    return os.path.join(profile["dir"], *parts)


def delete_session(sid):
    path = os.path.join(DATA_DIR, sid)
    if os.path.isdir(path):
        shutil.rmtree(path, ignore_errors=True)


def list_session_ids():
    if not os.path.isdir(DATA_DIR):
        return []
    return sorted(
        d for d in os.listdir(DATA_DIR)
        if os.path.isdir(os.path.join(DATA_DIR, d))
    )


def _coverages():
    return _CATEGORIES
