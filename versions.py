import json
import os
from datetime import datetime, timezone

MAX_VERSIONS = 40


def _now():
    return datetime.now(timezone.utc).isoformat()


def _versions_dir(profile):
    return os.path.join(profile["dir"], "versions")


def _version_path(profile, vid):
    return os.path.join(_versions_dir(profile), f"{vid}.json")


def _summary(profile):
    return {
        "phase": profile.get("phase"),
        "facts": len(profile.get("facts", []) or []),
        "directives": len(profile.get("interview_directives", []) or []),
        "turns": profile.get("turns", 0),
        "has_dossier": bool(profile.get("dossier")),
        "phrases": sum(1 for ph in profile.get("phrases", []) if ph.get("path")),
    }


def snapshot(profile, label="checkpoint"):
    """Persist the current profile as an undoable snapshot. Returns its id."""
    os.makedirs(_versions_dir(profile), exist_ok=True)
    vid = datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S%f")
    saved = dict(profile)
    saved.pop("dir", None)
    saved["_summary"] = _summary(profile)
    payload = {
        "id": vid,
        "ts": _now(),
        "label": (label or "checkpoint")[:80],
        "profile": saved,
    }
    tmp = _version_path(profile, vid) + ".tmp"
    with open(tmp, "w") as f:
        json.dump(payload, f, indent=2, default=str)
    os.replace(tmp, _version_path(profile, vid))

    for v in list_versions(profile)[MAX_VERSIONS:]:
        try:
            os.remove(_version_path(profile, v["id"]))
        except OSError:
            pass
    return {"id": vid, "ts": payload["ts"], "label": payload["label"]}


def list_versions(profile):
    d = _versions_dir(profile)
    if not os.path.isdir(d):
        return []
    out = []
    for fn in sorted(os.listdir(d)):
        if not fn.endswith(".json"):
            continue
        try:
            with open(os.path.join(d, fn)) as f:
                data = json.load(f)
            out.append({
                "id": data["id"],
                "ts": data["ts"],
                "label": data["label"],
                "summary": data["profile"].get("_summary", {}),
            })
        except Exception:
            continue
    out.sort(key=lambda v: v["ts"], reverse=True)
    return out


def restore(profile, vid):
    """Load a snapshot back into a profile dict (dir + id preserved)."""
    path = _version_path(profile, vid)
    if not os.path.exists(path):
        return None
    with open(path) as f:
        data = json.load(f)
    restored = dict(data["profile"])
    restored.pop("dir", None)
    restored["id"] = profile["id"]
    restored["dir"] = profile["dir"]
    return restored


def delete_version(profile, vid):
    try:
        os.remove(_version_path(profile, vid))
    except OSError:
        pass
