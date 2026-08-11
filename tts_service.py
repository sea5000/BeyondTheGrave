import hashlib
import os
import re
import threading
import time

import numpy as np
import soundfile as sf
import torch
from transformers import AutoModel, AutoProcessor

MODEL_ID = "Audio8/Audio8-TTS-Preview-0.6b"
MAX_CHARS = 140
GAP_SECONDS = 0.18

_lock = threading.Lock()
_model = None
_processor = None


def _load():
    global _model, _processor
    with _lock:
        if _model is not None:
            return
        device = "cuda" if torch.cuda.is_available() else "cpu"
        dtype = torch.bfloat16 if device == "cuda" else torch.float32
        _processor = AutoProcessor.from_pretrained(MODEL_ID, trust_remote_code=True)
        _model = AutoModel.from_pretrained(
            MODEL_ID, trust_remote_code=True, dtype=dtype,
        ).eval().to(device)


def _cache_path(session_dir, text):
    key = hashlib.md5(text.encode()).hexdigest()[:16]
    return os.path.join(session_dir, "generated", f"{key}.wav")


def _split_text(text, max_chars=MAX_CHARS):
    text = re.sub(r"\s+", " ", text.strip())
    if not text:
        return []
    if len(text) <= max_chars:
        return [text]
    sentences = re.split(r"(?<=[.!?…])\s+", text)
    segments = []
    cur = ""
    for s in sentences:
        if cur and len(cur) + len(s) + 1 > max_chars:
            segments.append(cur)
            cur = s
        else:
            cur = (cur + " " + s).strip() if cur else s
    if cur:
        segments.append(cur)
    final = []
    for seg in segments:
        if len(seg) <= max_chars:
            final.append(seg)
            continue
        words = seg.split(" ")
        cur = ""
        for w in words:
            if cur and len(cur) + len(w) + 1 > max_chars:
                final.append(cur)
                cur = w
            else:
                cur = (cur + " " + w).strip() if cur else w
        if cur:
            final.append(cur)
    return final


def _synthesize_segment(seg, reference_wav, reference_text, session_dir, device):
    cached = _cache_path(session_dir, seg)
    if os.path.exists(cached) and os.path.getsize(cached) > 1000:
        return cached
    inputs = _processor(
        text=[seg],
        reference_audio=[reference_wav],
        reference_text=[reference_text],
        return_tensors="pt",
    )
    inputs = {name: value.to(device) for name, value in inputs.items()}
    t0 = time.time()
    with torch.inference_mode():
        output = _model.generate(
            **inputs,
            max_new_tokens=2048,
            temperature=0.7,
            top_p=0.9,
            top_k=50,
            do_sample=True,
            return_dict_in_generate=True,
        )
        waveforms, waveform_lengths = _model.decode_audio(output.codes)
    audio = waveforms[0, : int(waveform_lengths[0])].float().cpu().numpy()
    os.makedirs(os.path.dirname(cached), exist_ok=True)
    sf.write(cached, audio, _model.config.codec_sample_rate)
    return cached


def synthesize(text, reference_wav, reference_text, session_dir):
    cached = _cache_path(session_dir, text)
    if os.path.exists(cached) and os.path.getsize(cached) > 1000:
        return cached

    _load()
    device = "cuda" if torch.cuda.is_available() else "cpu"
    segments = _split_text(text)
    if not segments:
        raise ValueError("empty text")

    segment_paths = [
        _synthesize_segment(seg, reference_wav, reference_text, session_dir, device)
        for seg in segments
    ]
    if len(segment_paths) == 1:
        return segment_paths[0]

    audios = []
    sr = None
    for path in segment_paths:
        data, s = sf.read(path)
        if sr is None:
            sr = s
        audios.append(data.astype(np.float32))
    gap = np.zeros(int(sr * GAP_SECONDS), dtype=np.float32)
    parts = []
    for i, data in enumerate(audios):
        if i:
            parts.append(gap)
        parts.append(data)
    merged = np.concatenate(parts)
    os.makedirs(os.path.dirname(cached), exist_ok=True)
    sf.write(cached, merged, sr)
    return cached
