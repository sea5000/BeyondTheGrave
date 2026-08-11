import os
import subprocess

SAMPLE_RATE = 44100


def convert_to_wav(src, dst):
    """Convert any browser upload (webm/opus/mp4) to 44.1kHz mono PCM WAV via ffmpeg."""
    cmd = [
        "ffmpeg", "-y", "-i", src,
        "-ar", str(SAMPLE_RATE), "-ac", "1", "-c:a", "pcm_s16le", dst,
    ]
    subprocess.run(cmd, check=True, capture_output=True)
    return dst


def save_upload(file_storage, dest_dir, stem):
    os.makedirs(dest_dir, exist_ok=True)
    raw = os.path.join(dest_dir, stem + ".webm")
    file_storage.save(raw)
    wav = os.path.join(dest_dir, stem + ".wav")
    convert_to_wav(raw, wav)
    try:
        os.remove(raw)
    except OSError:
        pass
    return wav
