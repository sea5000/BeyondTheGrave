# Beyond the Grave

A local web demo that interviews you about your life, captures your exact way of
speaking, and builds a **digital echo** — an AI that can talk about your life in
your voice, for your loved ones.

Everything runs locally. The interview LLM comes from **LM Studio** (OpenAI-compatible
endpoint) and the voice is synthesized with **Audio8 TTS** (zero-shot voice cloning).

## How it works

```
Browser (Flask-served single page)
   │  typed answers + voice recordings + clone chat + training
   ▼
Flask backend (python)
   ├─ interview.py    dynamic interviewer (12 life topics, coverage tracking,
   │                  fact extraction, follow-up questions)
   ├─ persona.py      dossier builder + the "echo" system prompt + phrase prompts
   ├─ llm.py          LM Studio client (JSON extraction; qwen3.5 thinking workaround)
   ├─ tts_service.py  Audio8-TTS-Preview-0.6b (zero-shot voice clone, GPU/CPU)
   ├─ audio.py        ffmpeg webm → 44.1kHz mono wav
   └─ storage.py      per-session JSON profile (data/sessions/<id>/)
```

The app opens on a **clone menu**: create a new clone from scratch, or load one of
your saved clones and pick up where you left off. Every profile is a separate person
— their interview, voice reference, recorded phrases, and memory are stored in their
own directory, so you can demo several people and voices side by side.

The interview is driven by a 12-topic guide (`topics.py`): identity, family, friends,
romance, career, life events, values, favorites, personality, speech style, wisdom,
and phrases. After every answer the model extracts concrete facts and updates a
per-topic coverage map, then picks the next question — usually a sharp follow-up on
what you just said, otherwise a probe into the least-covered topic. It actively mines
your *verbal identity* (expressions, catchphrases, pet words) because that's what makes
the echo sound like you.

**Training mode** lets you refine a finished clone. On the clone screen, switch on
"train mode" and tell the echo things to remember — a new story, a person's name, a
phrase you use. It extracts the facts, updates the coverage map, and rebuilds the
memory (dossier) file from everything it now knows.

Voice works in two layers:
1. **Recorded phrases** you speak aloud are stored verbatim and played back as-is
   (truest fidelity) whenever the exact text is spoken.
2. **New text** is synthesized by Audio8 using your reference clip (zero-shot cloning).
   Longer replies are split into short segments (Audio8's quality sweet spot) and
   stitched back together so prosody stays natural.

## Prerequisites

- Python 3.10+ (venv already created at `.venv`; uses the system Python 3.13)
- **LM Studio** running on `localhost:1234` with a chat model loaded
  (tested with `qwen/qwen3.5-9b`; `gemma-4-12b` and `deepseek-r1` also available).
- `ffmpeg` on PATH
- ~1.2GB of free GPU VRAM for TTS (falls back to CPU if no CUDA)

## Setup

```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
```

First TTS use downloads `Audio8/Audio8-TTS-Preview-0.6b` weights (~1.2GB).

## Run

```bash
./run.sh
# open http://localhost:5001
```

Then: from the **clone menu**, choose **Create a new clone** → consent → record your voice
reference → typed interview → speak a few phrases → build your echo → talk to it (or switch
on **train mode** to add memories later). Loaded clones resume wherever they left off.

## Configuration

- The AI model is selected from the **top bar dropdown**, available on every screen and
  switchable at any point mid-demo (default `qwen/qwen3.5-9b`). If LM Studio isn't
  reachable, a default list is offered instead.
- Saved clones live in `data/sessions/<id>/` and can be reopened, continued, or deleted
  from the home menu.
- LM Studio must be reachable at `http://localhost:1234` (configurable at the top of
  `llm.py`).

## Project layout

```
server.py          Flask app + routes
interview.py       interview engine (prompts, coverage, phases)
topics.py          the 12-topic interview guide / question bank
persona.py         fact grouping, dossier, clone system prompt, phrase prompts
llm.py             LM Studio client
tts_service.py     Audio8 synthesis wrapper
audio.py           upload → wav conversion
storage.py         session/profile persistence
static/            index.html, app.js, style.css
data/sessions/     per-person JSON profiles + audio (created at runtime)
```

## Notes & caveats

- Audio8 is a preview model; clone quality depends on a clean reference recording that
  matches the shown transcript.
- Everything is stored locally — nothing leaves this machine.
- The demo includes a consent/disclosure step because it builds a voice likeness.
