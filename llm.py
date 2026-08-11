import json
import re
import requests

BASE_URL = "http://localhost:1234/v1/chat/completions"
TIMEOUT = 300
PREFILL = "\n"

# Qwen3.5-family models always reason unless we prefill an empty think block;
# LM Studio drops the enable_thinking toggle on the OpenAI-compat path.
# Appending an assistant message with an empty think block makes reasoning_tokens=0.
SUPPRESS_THINKING = {"qwen3.5", "qwen35", "deepseek-r1"}

# Gemma 4 thinks by default and the reasoning is genuinely useful, so we keep it
# and give it headroom above the caller's answer budget (the caller's max_tokens
# stays the budget for the final answer). If thinking still starves the budget
# (finish_reason "length" with empty content) we retry once with more headroom.
KEEP_THINKING = {"gemma"}
THINK_HEADROOM = 1024


def _is_suppressed(model_id):
    low = (model_id or "").lower()
    return any(k in low for k in ["qwen3.5", "qwen35", "deepseek"])


def _keeps_thinking(model_id):
    low = (model_id or "").lower()
    return any(k in low for k in KEEP_THINKING)


def _strip_thought_blocks(text):
    if "<|channel>thought" not in text:
        return text
    return re.sub(
        r"<\|channel>thought.*?(?:<channel\|>|<\|channel>final)", "", text, flags=re.S
    )


def _chat(payload):
    resp = requests.post(BASE_URL, json=payload, timeout=TIMEOUT)
    resp.raise_for_status()
    data = resp.json()
    choice = data["choices"][0]
    message = choice.get("message", {})
    content = _strip_thought_blocks(message.get("content") or "")
    reasoning = message.get("reasoning_content") or ""
    return content, reasoning, choice.get("finish_reason")


def complete(model, messages, max_tokens=700, temperature=0.7):
    msgs = [dict(m) for m in messages]
    if _is_suppressed(model):
        msgs.append({"role": "assistant", "content": PREFILL})
    payload = {
        "model": model,
        "messages": msgs,
        "temperature": temperature,
        "max_tokens": max_tokens,
    }
    if _keeps_thinking(model):
        payload["max_tokens"] = max_tokens + THINK_HEADROOM

    content, reasoning, finished = _chat(payload)
    if (
        _keeps_thinking(model)
        and not content
        and reasoning
        and finished == "length"
    ):
        payload["max_tokens"] = max_tokens + THINK_HEADROOM * 2
        content, reasoning, finished = _chat(payload)
    return content.strip()


def _extract_json(text):
    text = re.sub(r"```(?:json)?", "", text).strip()
    start, end = text.find("{"), text.rfind("}")
    if start == -1 or end == -1:
        return None
    try:
        return json.loads(text[start : end + 1])
    except Exception:
        return None


def complete_json(model, messages, max_tokens=900, temperature=0.7):
    text = complete(model, messages, max_tokens=max_tokens, temperature=temperature)
    parsed = _extract_json(text)
    if parsed is None:
        # tolerate a plain-text reply
        return {"reply": text, "facts": [], "coverage": None, "phase": "interview"}
    return parsed


def list_models():
    try:
        resp = requests.get("http://localhost:1234/v1/models", timeout=10)
        resp.raise_for_status()
        return [m["id"] for m in resp.json().get("data", [])]
    except Exception:
        return []
