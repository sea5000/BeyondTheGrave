import hashlib
import os
import re
import threading
import time

import numpy as np
import soundfile as sf
import torchaudio

MODEL_ID = "ResembleAI/chatterbox-nano"
MAX_CHARS = 140
GAP_SECONDS = 0.18
MIN_REF_SECONDS = 5.0
DEVICE = "cpu"

_lock = threading.Lock()
_model = None


def _load():
    global _model
    with _lock:
        if _model is not None:
            return
        # lazy import keeps server startup fast and avoids heavy deps at import time
        import types

        import torch
        from chatterbox.tts_turbo import ChatterboxTurboTTS

        _model = ChatterboxTurboTTS.from_pretrained(device=DEVICE, nano=True)
        # librosa returns float64 audio; the S3 tokenizer's mel filters are float32,
        # so force its reference-audio path to float32 (avoids a Double@Float matmul error).
        tok = _model.s3gen.tokenizer

        def _prepare_audio_f32(self, wavs):
            out = []
            for wav in wavs:
                if isinstance(wav, np.ndarray):
                    wav = torch.from_numpy(wav)
                wav = wav.float()
                if wav.dim() == 1:
                    wav = wav.unsqueeze(0)
                out.append(wav)
            return out

        tok._prepare_audio = types.MethodType(_prepare_audio_f32, tok)
        # the voice encoder's LSTM also requires float32 reference audio
        ve = _model.ve
        _orig_efw = ve.embeds_from_wavs

        def _embeds_from_wavs_f32(self, wavs, sample_rate=None, **kwargs):
            wavs = [
                w.astype(np.float32) if isinstance(w, np.ndarray) else w for w in wavs
            ]
            return _orig_efw(wavs, sample_rate=sample_rate, **kwargs)

        ve.embeds_from_wavs = types.MethodType(_embeds_from_wavs_f32, ve)


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


def _synthesize_segment(seg, reference_wav, session_dir):
    cached = _cache_path(session_dir, seg)
    if os.path.exists(cached) and os.path.getsize(cached) > 1000:
        return cached
    t0 = time.time()
    wav = _model.generate(
        seg,
        audio_prompt_path=reference_wav,
        temperature=0.8,
        top_p=0.95,
        repetition_penalty=1.2,
    )
    print(f"[tts] '{seg[:40]}...' generated in {time.time() - t0:.1f}s")
    os.makedirs(os.path.dirname(cached), exist_ok=True)
    torchaudio.save(cached, wav, _model.sr)
    return cached


def synthesize(text, reference_wav, reference_text, session_dir):
    cached = _cache_path(session_dir, text)
    if os.path.exists(cached) and os.path.getsize(cached) > 1000:
        return cached

    _load()
    info = sf.info(reference_wav)
    if info.duration < MIN_REF_SECONDS:
        raise ValueError(
            f"reference voice must be at least {MIN_REF_SECONDS:.0f} seconds "
            f"(recorded {info.duration:.1f}s)"
        )
    segments = _split_text(text)
    if not segments:
        raise ValueError("empty text")

    segment_paths = [
        _synthesize_segment(seg, reference_wav, session_dir) for seg in segments
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
