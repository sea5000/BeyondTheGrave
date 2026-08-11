import json
import re

import llm
import storage
from topics import CATEGORIES, GUIDE

CATEGORY_KEYS = [c[0] for c in CATEGORIES]
MIN_TURNS_BEFORE_COMPLETE = 8
MAX_TURNS = 22
COMPLETE_THRESHOLD = 0.62
HISTORY_WINDOW = 16

MISSION = """You are the interviewer for "Beyond the Grave", a guided experience that captures a
person's life, identity, and voice so an AI can later speak and answer questions as them for their
loved ones. You are conducting a deep, warm, personal interview. Your job is to ask ONE question
at a time and, through follow-up questions, gather as many specific, concrete personal details as
possible: names, dates, places, stories, feelings, beliefs, relationships, and - critically - the
person's exact way of speaking.

Interview style rules:
- Ask ONE question at a time. Never list questions.
- Most of the time, ask a sharp follow-up on what they just said to dig deeper. Push past surface
  answers: ask for the story, the exact words, the sensory detail, the person involved, what it
  felt like. A good follow-up is specific to what they just said, not generic.
- When the current thread is mined out, move to a category with LOW coverage. Read that category's
  guide questions and rephrase one in a natural, personal way.
- Vary your style so it feels like a thoughtful friend, never a form or an interrogation.
- Occasionally reflect something they told you, then ask the next question.
- Proactively capture their verbal identity: ask how they phrase things, their expressions,
  catchphrases, sayings, humor. Ask for exact wording.
- NEVER ask a question that presupposes facts you don't know yet. Don't assume they chose their own
  name ("why did you choose your name" is wrong - they may not have chosen it), and don't assume a
  partner, children, or siblings. Phrase neutrally: "Is there a story behind your name?" or "Do you
  have siblings?" rather than "How many siblings do you have?"
- Keep your reply warm, human, and under ~35 words."""


def build_system_prompt(profile):
    cov = json.dumps(profile.get("topics_coverage", {}), indent=2)
    guide_lines = []
    for key, title, target in CATEGORIES:
        desc, questions = GUIDE[key]
        guide_lines.append(
            f"## {title} (target coverage {target})\n{desc}\nSeed questions: {json.dumps(questions)}"
        )
    guide = "\n\n".join(guide_lines)
    return (
        MISSION
        + "\n\n# INTERVIEW GUIDE (draw from these, always rephrase)\n"
        + guide
        + "\n\n# CURRENT COVERAGE\n"
        + cov
    )


def history_messages(profile):
    msgs = []
    turns = profile.get("transcript", [])[-HISTORY_WINDOW:]
    # qwen's template requires every assistant message to be preceded by a user message.
    if turns and turns[0]["role"] == "assistant":
        msgs.append({"role": "user", "content": "[conversation continues]"})
    for turn in turns:
        msgs.append({"role": turn["role"], "content": turn["content"]})
    return msgs


EXTRACT_SYSTEM = """You are the data analyst for a personal-archival interview. A human interviewer
asked a question, and the person answered. Extract from the ANSWER every concrete, useful personal
detail that would help an AI later speak convincingly as this person: names, relationships, dates,
places, occupations, beliefs, values, stories, preferences, personality traits, and especially any
EXACT phrases, sayings, or expressions the person used (their verbal identity matters most).

Return a single JSON object, no markdown, no commentary, with exactly these fields:
- "facts": array of objects, each {"category": string, "fact": string, "importance": integer 1-5}.
  Categories (use only these): identity, family, friends, romance, career, life_events, values,
  favorites, personality, speech_style, wisdom, phrases. Each fact must be a specific, self-contained
  statement (e.g. "Sister's name is Emily"). Capture exact quotes of how they speak verbatim.
- "coverage": object mapping every one of the 12 categories above to a 0..1 estimate of how well it
  is covered SO FAR, given the existing coverage below and the new answer. Update honestly."""


# Normalize facts like "Sister Amy says 'cool beans'." or "My mom used to say 'patience'."
# into the person's own phrasing so the clone speaks them, not quotes them.
_REPORTED_SPEECH = re.compile(
    r"^\s*(?:(?:my|the)\s+)?(?:[A-Z]?[a-zA-Z]+\s+)*(?:used\s+to\s+)?(?:always\s+|really\s+)?(?:says?|said|would\s+say)\s+[\"'](.+?)[\"']\s*\.?\s*$",
    re.IGNORECASE | re.DOTALL,
)


def _normalize_fact(category, fact):
    if category not in ("speech_style", "phrases"):
        return fact
    m = _REPORTED_SPEECH.match(fact)
    if m:
        phrase = m.group(1).strip()
        if phrase:
            return f'Uses the phrase "{phrase}".'
    return fact


def extract(model, question, answer, coverage):
    cov = json.dumps(coverage, indent=2)
    user = f"Existing coverage:\n{cov}\n\nInterviewer asked:\n{question}\n\nThe person answered:\n{answer}"
    return llm.complete_json(
        model,
        [{"role": "system", "content": EXTRACT_SYSTEM}, {"role": "user", "content": user}],
        max_tokens=700,
        temperature=0.2,
    )


def _fallback_question(profile):
    """Deterministic recovery question from the least-covered category."""
    cov = profile.get("topics_coverage", {})
    lowest = min(CATEGORIES, key=lambda c: cov.get(c[0], 0.0))[0]
    _, questions = GUIDE[lowest]
    if questions:
        return questions[0]
    return "Tell me more about that."


def start(profile):
    msgs = [{"role": "system", "content": build_system_prompt(profile)}]
    msgs += history_messages(profile)
    msgs.append({
        "role": "user",
        "content": (
            f"[BEGIN INTERVIEW] My name is {profile['name']}. Ask me your first question. Open with a"
            " warm, easy icebreaker anyone can answer — for example where I grew up, someone I love,"
            " or a memory that makes me happy. Do NOT ask about my name first."
        ),
    })
    reply = llm.complete(profile["model"], msgs, max_tokens=400, temperature=0.7).strip()
    if not reply:
        reply = f"It's lovely to meet you, {profile['name']}. Tell me about yourself - where did you grow up?"
    storage.add_transcript(profile, "assistant", reply)
    profile["turns"] += 1
    storage.save_profile(profile)
    return {"reply": reply, "phase": profile["phase"], "turns": profile["turns"], "coverage": profile["topics_coverage"]}


def process_turn(profile, user_text):
    storage.add_transcript(profile, "user", user_text)
    question = user_text  # the "question" being answered is the last assistant message
    for t in reversed(profile["transcript"]):
        if t["role"] == "assistant":
            question = t["content"]
            break

    # 1) extraction (separate JSON-only call, no chat history -> reliable JSON)
    result = extract(profile["model"], question, user_text, profile.get("topics_coverage", {}))
    _apply_meta(profile, result)

    # 2) next question (plain chat, imitates conversation style)
    msgs = [{"role": "system", "content": build_system_prompt(profile)}]
    msgs += history_messages(profile)
    reply = llm.complete(profile["model"], msgs, max_tokens=400, temperature=0.75).strip()
    if not reply:
        reply = _fallback_question(profile)
    storage.add_transcript(profile, "assistant", reply)

    profile["turns"] += 1
    _maybe_complete(profile)
    storage.save_profile(profile)

    return {
        "reply": reply,
        "facts": result.get("facts", []),
        "coverage": profile["topics_coverage"],
        "phase": profile["phase"],
        "turns": profile["turns"],
    }


def _apply_meta(profile, result):
    facts = []
    for f in result.get("facts", []) or []:
        if not isinstance(f, dict):
            continue
        cat = f.get("category") if isinstance(f.get("category"), str) else ""
        if cat not in CATEGORY_KEYS:
            cat = "identity"
        fact = str(f.get("fact", "")).strip()
        if not fact:
            continue
        imp = str(f.get("importance", 3))
        try:
            importance = max(1, min(5, int(float(imp))))
        except (TypeError, ValueError):
            importance = 3
        fact = _normalize_fact(cat, fact)
        facts.append({"category": cat, "fact": fact, "importance": importance})
    if facts:
        profile.setdefault("facts", []).extend(facts)

    cov = result.get("coverage")
    if isinstance(cov, dict):
        merged = dict(profile.get("topics_coverage", {}))
        for cat, val in cov.items():
            if cat in CATEGORY_KEYS:
                try:
                    v = float(val)
                except (TypeError, ValueError):
                    continue
                merged[cat] = max(merged.get(cat, 0.0), min(1.0, v))
        profile["topics_coverage"] = merged


def _maybe_complete(profile):
    if profile["phase"] != "interview":
        return
    cov = profile.get("topics_coverage", {})
    vals = [cov.get(c, 0.0) for c in CATEGORY_KEYS]
    avg = sum(vals) / len(vals) if vals else 0.0
    if profile["turns"] >= MAX_TURNS:
        profile["phase"] = "phrases"
    elif profile["turns"] >= MIN_TURNS_BEFORE_COMPLETE and avg >= COMPLETE_THRESHOLD:
        profile["phase"] = "phrases"


def finish_interview(profile):
    profile["phase"] = "phrases"
    storage.save_profile(profile)
    return {"phase": profile["phase"]}
