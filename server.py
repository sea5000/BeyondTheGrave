import os
import re
import uuid

import soundfile as sf
from flask import Flask, jsonify, request, send_from_directory
from flask_cors import CORS

import audio
import interview
import llm
import persona
import storage
import tts_service
import versions

app = Flask(__name__, static_folder="static", static_url_path="")
CORS(app)

DATA_SESSIONS = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data", "sessions")


@app.get("/")
def index():
    return send_from_directory("static", "index.html")


@app.get("/api/health")
def health():
    return jsonify({"ok": True})


@app.get("/api/models")
def models():
    ids = llm.list_models()
    llms = [m for m in ids if "embedding" not in m]
    return jsonify({"models": llms})


@app.get("/api/profiles")
def profiles():
    items = []
    for sid in storage.list_session_ids():
        p = storage.load_profile(sid)
        if not p:
            continue
        items.append({
            "id": p["id"],
            "name": p["name"],
            "phase": p["phase"],
            "model": p["model"],
            "created": p.get("created"),
            "updated": p.get("updated"),
            "has_voice_ref": p.get("voice_ref") is not None,
            "phrases_recorded": sum(1 for ph in p.get("phrases", []) if ph.get("path")),
            "has_dossier": bool(p.get("dossier")),
            "facts": len(p.get("facts", [])),
            "turns": p.get("turns", 0),
        })
    items.sort(key=lambda x: x.get("updated") or x.get("created") or "", reverse=True)
    return jsonify({"profiles": items})


@app.post("/api/session")
def create_session():
    data = request.get_json(silent=True) or {}
    name = (data.get("name") or "").strip()
    model = data.get("model") or "qwen/qwen3.5-9b"
    profile = storage.create_session(name, model)
    return jsonify({"session_id": profile["id"]})


@app.post("/api/session/<sid>/model")
def set_model(sid):
    profile = storage.load_profile(sid)
    if not profile:
        return jsonify({"error": "session not found"}), 404
    data = request.get_json(silent=True) or {}
    model = (data.get("model") or "").strip()
    if not model:
        return jsonify({"error": "model is required"}), 400
    profile["model"] = model
    storage.save_profile(profile)
    return jsonify({"ok": True, "model": model})


@app.delete("/api/session/<sid>")
def delete_session(sid):
    storage.delete_session(sid)
    return jsonify({"ok": True})


def _public_profile(profile):
    return {
        "id": profile["id"],
        "name": profile["name"],
        "model": profile["model"],
        "phase": profile["phase"],
        "coverage": profile["topics_coverage"],
        "facts": profile["facts"][-40:],
        "transcript": profile["transcript"],
        "has_voice_ref": profile.get("voice_ref") is not None,
        "voice_ref_text": (profile.get("voice_ref") or {}).get("text"),
        "phrases": [
            {
                "id": ph["id"],
                "text": ph.get("text"),
                "hint": ph.get("hint"),
                "source": ph.get("source"),
                "recorded": ph.get("path") is not None,
                "url": _audio_url(profile, ph["path"]) if ph.get("path") else None,
            }
            for ph in profile.get("phrases", [])
        ],
        "phrase_prompts": profile.get("phrase_prompts", []),
        "dossier": profile.get("dossier"),
        "directives": profile.get("interview_directives", []),
        "turns": profile.get("turns", 0),
    }


def _audio_url(profile, rel):
    if not rel:
        return None
    return f"/api/session/{profile['id']}/audio/{rel}"


@app.get("/api/session/<sid>/state")
def get_state(sid):
    profile = storage.load_profile(sid)
    if not profile:
        return jsonify({"error": "session not found"}), 404
    return jsonify(_public_profile(profile))


@app.post("/api/session/<sid>/voice/reference")
def upload_reference(sid):
    profile = storage.load_profile(sid)
    if not profile:
        return jsonify({"error": "session not found"}), 404
    f = request.files.get("file")
    text = (request.form.get("text") or "").strip()
    if not f or not text:
        return jsonify({"error": "audio file and exact transcript text are required"}), 400
    try:
        wav = audio.save_upload(f, storage.session_abs_path(profile, "voice"), "ref")
    except Exception as e:
        return jsonify({"error": f"audio conversion failed: {e}"}), 500
    try:
        dur = sf.info(wav).duration
    except Exception as e:
        return jsonify({"error": f"could not read recorded audio: {e}"}), 500
    if dur < 5.0:
        os.remove(wav)
        return jsonify({"error": f"reference voice must be at least 5 seconds long (recorded {dur:.1f}s)"}), 400
    profile["voice_ref"] = {"path": storage._rel(profile, wav), "text": text}
    storage.save_profile(profile)
    return jsonify({"ok": True, "path": profile["voice_ref"]["path"]})


@app.post("/api/session/<sid>/voice/phrase")
def upload_phrase(sid):
    profile = storage.load_profile(sid)
    if not profile:
        return jsonify({"error": "session not found"}), 404
    f = request.files.get("file")
    pid = request.form.get("prompt_id") or f"c{uuid.uuid4().hex[:6]}"
    text = (request.form.get("text") or "").strip()
    hint = request.form.get("hint") or ""
    source = request.form.get("source") or "recite"
    if not f:
        return jsonify({"error": "audio file is required"}), 400
    if not text and source == "recite":
        return jsonify({"error": "recited phrase needs its exact text"}), 400
    try:
        wav = audio.save_upload(f, storage.session_abs_path(profile, "voice"), f"phrase_{pid}")
    except Exception as e:
        return jsonify({"error": f"audio conversion failed: {e}"}), 500
    entry = {
        "id": pid,
        "text": text or None,
        "hint": hint,
        "source": source,
        "path": storage._rel(profile, wav),
        "url": _audio_url(profile, storage._rel(profile, wav)),
    }
    phrases = profile.setdefault("phrases", [])
    phrases = [p for p in phrases if p["id"] != pid]
    phrases.append(entry)
    profile["phrases"] = phrases
    storage.save_profile(profile)
    return jsonify(entry)


@app.post("/api/session/<sid>/interview/start")
def interview_start(sid):
    profile = storage.load_profile(sid)
    if not profile:
        return jsonify({"error": "session not found"}), 404
    if profile.get("phase") in ("setup",):
        profile["phase"] = "interview"
        storage.save_profile(profile)
    try:
        result = interview.start(profile)
        return jsonify(result)
    except Exception as e:
        return jsonify({"error": f"interview failed: {e}"}), 500


@app.post("/api/session/<sid>/interview")
def interview_turn(sid):
    profile = storage.load_profile(sid)
    if not profile:
        return jsonify({"error": "session not found"}), 404
    data = request.get_json(silent=True) or {}
    message = (data.get("message") or "").strip()
    if not message:
        return jsonify({"error": "message is required"}), 400
    if profile.get("phase") != "interview":
        return jsonify({"error": "interview not active", "phase": profile.get("phase")}), 400
    try:
        return jsonify(interview.process_turn(profile, message))
    except Exception as e:
        return jsonify({"error": f"interview failed: {e}"}), 500


@app.post("/api/session/<sid>/finish")
def finish(sid):
    profile = storage.load_profile(sid)
    if not profile:
        return jsonify({"error": "session not found"}), 404
    profile["phase"] = "phrases"
    prompts = persona.build_phrase_prompts(profile)
    profile["phrase_prompts"] = prompts
    storage.save_profile(profile)
    return jsonify({"phase": "phrases", "phrase_prompts": prompts})


@app.post("/api/session/<sid>/interview/resume")
def interview_resume(sid):
    profile = storage.load_profile(sid)
    if not profile:
        return jsonify({"error": "session not found"}), 404
    profile["phase"] = "interview"
    storage.save_profile(profile)
    return jsonify({"phase": "interview", "coverage": profile["topics_coverage"]})


@app.get("/api/session/<sid>/directives")
def list_directives(sid):
    profile = storage.load_profile(sid)
    if not profile:
        return jsonify({"error": "session not found"}), 404
    return jsonify({"directives": profile.get("interview_directives", [])})


@app.post("/api/session/<sid>/directives")
def add_directive(sid):
    profile = storage.load_profile(sid)
    if not profile:
        return jsonify({"error": "session not found"}), 404
    data = request.get_json(silent=True) or {}
    text = (data.get("text") or "").strip()
    if not text:
        return jsonify({"error": "directive is required"}), 400
    d = {"id": uuid.uuid4().hex[:8], "text": text, "created": storage._now()}
    profile.setdefault("interview_directives", []).append(d)
    storage.save_profile(profile)
    versions.snapshot(profile, "directive added")
    return jsonify(d)


@app.delete("/api/session/<sid>/directives/<did>")
def remove_directive(sid, did):
    profile = storage.load_profile(sid)
    if not profile:
        return jsonify({"error": "session not found"}), 404
    profile["interview_directives"] = [
        d for d in profile.get("interview_directives", []) if d.get("id") != did
    ]
    storage.save_profile(profile)
    versions.snapshot(profile, "directive removed")
    return jsonify({"ok": True, "directives": profile["interview_directives"]})


@app.get("/api/session/<sid>/versions")
def get_versions(sid):
    profile = storage.load_profile(sid)
    if not profile:
        return jsonify({"error": "session not found"}), 404
    return jsonify({"versions": versions.list_versions(profile)})


@app.post("/api/session/<sid>/versions")
def save_checkpoint(sid):
    profile = storage.load_profile(sid)
    if not profile:
        return jsonify({"error": "session not found"}), 404
    data = request.get_json(silent=True) or {}
    v = versions.snapshot(profile, (data.get("label") or "checkpoint").strip()[:80])
    return jsonify({"ok": True, "version": v})


@app.post("/api/session/<sid>/versions/<vid>/restore")
def restore_version(sid, vid):
    profile = storage.load_profile(sid)
    if not profile:
        return jsonify({"error": "session not found"}), 404
    restored = versions.restore(profile, vid)
    if restored is None:
        return jsonify({"error": "version not found"}), 404
    versions.snapshot(profile, "before restore")
    storage.save_profile(restored)
    return jsonify(_public_profile(restored))


@app.delete("/api/session/<sid>/versions/<vid>")
def delete_version(sid, vid):
    profile = storage.load_profile(sid)
    if not profile:
        return jsonify({"error": "session not found"}), 404
    versions.delete_version(profile, vid)
    return jsonify({"ok": True})


@app.post("/api/session/<sid>/dossier")
def dossier(sid):
    profile = storage.load_profile(sid)
    if not profile:
        return jsonify({"error": "session not found"}), 404
    try:
        text = persona.build_dossier(profile)
    except Exception as e:
        return jsonify({"error": f"dossier failed: {e}"}), 500
    profile["phase"] = "ready"
    storage.save_profile(profile)
    versions.snapshot(profile, "memory built")
    return jsonify({"dossier": text, "phase": "ready"})


@app.post("/api/session/<sid>/clone/chat")
def clone_chat(sid):
    profile = storage.load_profile(sid)
    if not profile:
        return jsonify({"error": "session not found"}), 404
    data = request.get_json(silent=True) or {}
    message = (data.get("message") or "").strip()
    if not message:
        return jsonify({"error": "message is required"}), 400
    sys = persona.clone_system_prompt(profile)
    history = profile.get("clone_history", [])
    msgs = [{"role": "system", "content": sys}]
    if history and history[0]["role"] == "assistant":
        msgs.append({"role": "user", "content": "[conversation begins]"})
    msgs += history[-12:] + [{"role": "user", "content": message}]
    try:
        reply = llm.complete(profile["model"], msgs, max_tokens=280, temperature=0.75)
    except Exception as e:
        return jsonify({"error": f"clone chat failed: {e}"}), 500
    if not reply:
        reply = "Give me a moment - I'm still finding the right words for that."
    profile.setdefault("clone_history", []).extend(
        [{"role": "user", "content": message}, {"role": "assistant", "content": reply}]
    )
    storage.save_profile(profile)
    return jsonify({"reply": reply})


@app.post("/api/session/<sid>/train")
def train(sid):
    profile = storage.load_profile(sid)
    if not profile:
        return jsonify({"error": "session not found"}), 404
    if profile.get("phase") not in ("interview", "phrases", "ready"):
        return jsonify({"error": "train mode not available in this phase", "phase": profile.get("phase")}), 400
    data = request.get_json(silent=True) or {}
    message = (data.get("message") or "").strip()
    if not message:
        return jsonify({"error": "message is required"}), 400
    try:
        result = persona.train_extract(profile["model"], message, profile.get("topics_coverage", {}))
        interview._apply_meta(profile, result)
        profile.setdefault("train_log", []).append({
            "user": message,
            "facts": result.get("facts", []),
            "ts": storage._now(),
        })
        dossier = persona.build_dossier(profile)
    except Exception as e:
        return jsonify({"error": f"train failed: {e}"}), 500
    profile["phase"] = "ready"
    storage.save_profile(profile)
    versions.snapshot(profile, "after training")
    facts = result.get("facts", []) or []
    lines = [f"- {f['fact']}" for f in facts if f.get("fact")]
    if lines:
        reply = "I've folded that into your memory.\n" + "\n".join(lines[:8]) + "\nAnything else you'd like to add or change?"
    else:
        reply = "I didn't catch any new facts from that. Tell me something specific — a story, a person, a phrase you like — and I'll add it to your memory."
    return jsonify({
        "reply": reply,
        "facts": facts,
        "coverage": profile["topics_coverage"],
        "dossier": dossier,
        "phase": profile["phase"],
    })


@app.post("/api/session/<sid>/tts")
def speak(sid):
    profile = storage.load_profile(sid)
    if not profile:
        return jsonify({"error": "session not found"}), 404
    data = request.get_json(silent=True) or {}
    text = (data.get("text") or "").strip()
    if not text:
        return jsonify({"error": "text is required"}), 400
    # Prefer an authentic recording when the exact text was captured.
    for ph in profile.get("phrases", []):
        if ph.get("text") and _norm(ph["text"]) == _norm(text):
            return jsonify({"url": _audio_url(profile, ph["path"]), "mode": "recorded"})
    ref = profile.get("voice_ref")
    if not ref or not os.path.exists(storage.session_abs_path(profile, ref["path"])):
        return jsonify({"error": "reference voice not recorded"}), 400
    try:
        wav = tts_service.synthesize(
            text,
            storage.session_abs_path(profile, ref["path"]),
            ref["text"],
            profile["dir"],
        )
    except Exception as e:
        return jsonify({"error": f"TTS failed: {e}"}), 500
    return jsonify({"url": _audio_url(profile, storage._rel(profile, wav)), "mode": "synthesized"})


@app.get("/api/session/<sid>/audio/<path:rel>")
def audio_file(sid, rel):
    profile = storage.load_profile(sid)
    if not profile:
        return jsonify({"error": "session not found"}), 404
    rel = rel.replace("\\", "/")
    if ".." in rel.split("/"):
        return jsonify({"error": "bad path"}), 400
    return send_from_directory(profile["dir"], rel, mimetype="audio/wav")


def _norm(s):
    return re.sub(r"[^a-z0-9]+", "", s.lower())


if __name__ == "__main__":
    app.run(host="127.0.0.1", port=5001, debug=True, threaded=True)
