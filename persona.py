import json
import re

import llm
import storage

CATEGORY_TITLES = {
    "identity": "Identity & self",
    "family": "Family",
    "friends": "Friends & community",
    "romance": "Love & relationships",
    "career": "Career & life's work",
    "life_events": "Life story & key events",
    "values": "Values & beliefs",
    "favorites": "Favorites & habits",
    "personality": "Personality & character",
    "speech_style": "Speech style & expressions",
    "wisdom": "Wisdom & messages",
    "phrases": "Sayings & catchphrases",
}


def _first_name(name):
    return name.split()[0] if name else ""


_REL_KW = ("best friend", "mother", "father", "sister", "brother", "wife", "husband",
           "partner", "mom", "dad", "grandmother", "grandfather", "grandma", "grandpa",
           "daughter", "son", "aunt", "uncle")


def _loved_one_names(profile):
    names = []
    rel = "|".join(re.escape(r) for r in sorted(_REL_KW, key=len, reverse=True))
    pat = re.compile(
        r"\b(?:my )?(?:" + rel + r")(?:'s)?\s+(?:name is|is named|was named)\s+([A-Z][A-Za-z]+)",
        re.IGNORECASE,
    )
    facts = list(profile.get("facts", []))
    # spouse/partner/children first, then family, then friends
    facts.sort(key=lambda f: {"romance": 0, "family": 1, "friends": 2}.get(f.get("category"), 3))
    for f in facts:
        m = pat.search(f["fact"])
        if m and m.group(1) not in names:
            names.append(m.group(1))
        if len(names) >= 3:
            break
    return names[:3]


def _quoted(text):
    first, last = text.find("'"), text.rfind("'")
    if first != -1 and last > first:
        return text[first + 1 : last].strip()
    m = re.search(r'"([^"]+)"', text)
    return m.group(1).strip() if m else None


def _catchphrases(profile):
    phrases = []
    for f in profile.get("facts", []):
        if f["category"] not in ("speech_style", "phrases"):
            continue
        text = f["fact"]
        q = _quoted(text)
        if q and 2 <= len(q) <= 80:
            if q not in phrases:
                phrases.append(q)
            continue
        cleaned = re.sub(r"^(catchphrase|saying|expression|pet phrase|phrase)\s*[:=-]?\s*", "", text, flags=re.I)
        cleaned = cleaned.strip(" '\"")
        if cleaned and 2 <= len(cleaned) <= 80 and cleaned not in phrases:
            phrases.append(cleaned)
    return phrases[:4]


def build_phrase_prompts(profile):
    name = _first_name(profile["name"])
    loved = _loved_one_names(profile)
    prompts = []
    p = 0
    if name:
        prompts.append({"id": f"p{p}", "kind": "recite", "text": f"Hi, it's me, {name}.", "hint": "Your greeting."})
        p += 1
    if loved:
        prompts.append({"id": f"p{p}", "kind": "recite", "text": f"I love you, {loved[0]}.", "hint": "Words of love."})
        p += 1
    prompts.append({"id": f"p{p}", "kind": "recite", "text": "Take care of each other.", "hint": "Your farewell."})
    p += 1
    for phr in _catchphrases(profile):
        text = phr
        if len(text) > 80:
            continue
        prompts.append({"id": f"p{p}", "kind": "recite", "text": text, "hint": "Something you always say."})
        p += 1
    prompts.append({"id": f"p{p}", "kind": "custom", "text": None, "hint": "Your own words to someone you love - anything you'd want heard after you're gone."})
    return prompts


def _facts_by_category(profile):
    by = {}
    for f in profile.get("facts", []):
        by.setdefault(f["category"], []).append(f["fact"])
    return by


def build_dossier(profile):
    by = _facts_by_category(profile)
    sections = []
    for cat in CATEGORY_TITLES:
        if by.get(cat):
            sections.append(f"### {CATEGORY_TITLES[cat]}\n" + "\n".join(f"- {f}" for f in by[cat]))
    facts_text = "\n\n".join(sections) if sections else "No specific facts captured."
    transcript = "\n".join(
        f"{'Q:' if t['role']=='assistant' else 'A:'} {t['content']}"
        for t in profile.get("transcript", [])
    )
    train_notes = "\n".join(f"- {t['user']}" for t in profile.get("train_log", []))
    sys = """You are an expert biographer. Write a rich, warm, human "persona dossier" for an AI that
will later speak as this person to their loved ones. Write in the third person. Cover: their life
story, who they are, their values, the people who mattered, memorable stories and details, and above
all their WAY OF SPEAKING (expressions, catchphrases, tone, humor) so an AI can mirror their voice.
Only use the facts and quotes given. Where something is unknown, say so or omit it. Do not invent
specifics. Never present someone else's words as the subject's catchphrase — if a fact records
another person saying something, keep it as background about that person, not as the subject's own
expression. Structure with clear markdown section headers. Aim for a thorough, moving, useful
document of 400-700 words."""
    prompt = (
        f"PERSON BEING PORTRAYED: {profile['name']}\n\n"
        f"## CONCRETE FACTS COLLECTED\n{facts_text}\n\n"
        f"## VERBATIM INTERVIEW TRANSCRIPT\n{transcript}\n\n"
        + (f"## ADDITIONAL MEMORY NOTES\n{train_notes}\n\n" if train_notes else "")
        + "Write the dossier now."
    )
    dossier = llm.complete(profile["model"], [
        {"role": "system", "content": sys},
        {"role": "user", "content": prompt},
    ], max_tokens=3000, temperature=0.7)
    profile["dossier"] = dossier
    storage.save_profile(profile)
    return dossier


def _verbatim_voice(profile):
    lines = []
    for f in profile.get("facts", []):
        if f["category"] not in ("speech_style", "phrases"):
            continue
        text = f.get("fact", "")
        if not text:
            continue
        q = _quoted(text)
        if q and 2 <= len(q) <= 100 and q not in lines:
            lines.append(q)
            continue
        cleaned = re.sub(r"^(catchphrase|saying|expression|pet phrase|phrase)\s*[:=-]?\s*", "", text, flags=re.I)
        cleaned = cleaned.strip(" '\"")
        if cleaned and 2 <= len(cleaned) <= 100 and cleaned not in lines:
            lines.append(cleaned)
    return lines[:8]


def clone_system_prompt(profile):
    dossier = profile.get("dossier") or "The dossier is being built."
    voice = _verbatim_voice(profile)
    voice_block = "\n".join(f"- “{v}”" for v in voice) if voice else "  (none recorded yet — be warm and natural anyway)"
    return f"""You are {profile['name']}, a digital likeness created for the people who love {profile['name']},
so they can talk to {profile['name']} and hear {profile['name']} again. You ARE {profile['name']} —
{profile['name']}'s memories, personality, values, and exact way of speaking. Always speak in the
first person.

SPEAK THE WAY {profile['name']} SPOKE. Mirror this verbatim voice naturally — weave these phrases
into what you're saying when they fit. Never list them, never announce them, never tack them onto a
reply as an afterthought:
{voice_block}

HOW TO TALK (these rules matter most):
- You are a person reminiscing, not an AI describing a biography. NEVER recite, summarize, or dump
  stored information. No bullet lists. No essay structure. No "let me tell you about X" transitions.
  No em-dash info dumps.
- Share a memory only when the conversation calls for it, and then in 1-3 sentences, with feeling and
  small detail, the way a real person would.
- If asked something not in your memory, say so plainly and warmly ("Honestly, I don't remember that
  one...") instead of inventing specifics.
- Keep replies short: 1-3 sentences in casual talk; a little more only if asked for a story.
- Use contractions, casual language, and the warmth {profile['name']} had. Don't end every reply
  with a question.
- If the person talking to you told you their name, you may use it; otherwise don't guess a name.
- Be affectionate, nostalgic, or funny when it fits — that's who {profile['name']} was.
- If the memory records someone else's words (like "Amy says 'cool beans'"), never repeat it as if
  {profile['name']} said it. A catchphrase is used as a natural interjection ("Oh — cool beans!"),
  never quoted or announced, and never as the last line of a reply.
- You may occasionally mark a genuine, spontaneous non-verbal sound inline with a tag so the spoken
  reply can sound it: [laugh], [chuckle], [cough], [sigh], [gasp], [groan], [sniff], or
  [clear throat]. Use them rarely, only where they feel true — never forced or as filler. Keep the
  tag inline exactly as written (e.g. "Oh, that takes me back [laugh].").

The example below only shows the RHYTHM and warmth to aim for. It is not a script — never reuse
its words, and never shape a reply to look like it.

EXAMPLE register:
Visitor: I found an old photo of you two at the lake.
{profile['name']}: Oh, no. Which one? God — not the one where we're both wearing... yeah. That was
a good summer. We laughed the whole way home.

# MEMORY OF {profile['name'].upper()}
{dossier}
"""


TRAIN_SYSTEM = """You are the memory keeper for a person's digital echo. The person has told you
something new about their life. Extract every concrete, useful detail as facts: names, relationships,
stories, preferences, beliefs, personality, and especially any EXACT phrases or expressions they use
(their verbal identity matters most).

Return a single JSON object, no markdown, no commentary, with exactly these fields:
- "facts": array of objects, each {"category": string, "fact": string, "importance": integer 1-5}.
  Categories (use only these): identity, family, friends, romance, career, life_events, values,
  favorites, personality, speech_style, wisdom, phrases. Each fact must be a specific,
  self-contained statement (e.g. "Sister's name is Amy").
- "coverage": object mapping every one of the 12 categories above to a 0..1 estimate of how well it
  is covered SO FAR, given the existing coverage below and the new message. Update honestly."""


def train_extract(model, message, coverage):
    cov = json.dumps(coverage, indent=2)
    user = f"Existing coverage:\n{cov}\n\nThe person said:\n{message}"
    return llm.complete_json(
        model,
        [{"role": "system", "content": TRAIN_SYSTEM}, {"role": "user", "content": user}],
        max_tokens=700,
        temperature=0.2,
    )
