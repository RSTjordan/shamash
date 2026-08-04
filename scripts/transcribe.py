"""Transcribe an audio file to text on stdout. Fully local, no cloud API.

Only used when features.voice_notes is true. The model comes from
features.voice_model in config.json (default: a Hebrew-tuned CT2 build of
whisper-large-v3-turbo), with the stock large-v3-turbo as the fallback
candidate.

Usage: whisper-env\\Scripts\\python.exe scripts\\transcribe.py <audio-file>
"""

import os
import sys
from pathlib import Path

from faster_whisper import WhisperModel

sys.path.insert(0, str(Path(__file__).resolve().parent))
import config

# Windows consoles default to a legacy codepage — non-ASCII output would raise
# UnicodeEncodeError.
sys.stdout.reconfigure(encoding="utf-8", errors="replace")
sys.stderr.reconfigure(encoding="utf-8", errors="replace")

CFG = config.load()
MODELS_DIR = str(Path(CFG["root"]) / "whisper-env" / "models")
_PRIMARY = CFG["features"].get("voice_model") or "ivrit-ai/whisper-large-v3-turbo-ct2"
CANDIDATES = tuple(dict.fromkeys((_PRIMARY, "large-v3-turbo")))
# Most of the machine, not all of it — transcription must not starve whatever
# else is running.
CPU_THREADS = max(4, (os.cpu_count() or 4) - 2)


def main() -> int:
    if len(sys.argv) < 2:
        print("usage: transcribe.py <audio-file>", file=sys.stderr)
        return 2
    audio = sys.argv[1]
    for model_id in CANDIDATES:
        try:
            model = WhisperModel(
                model_id,
                device="cpu",
                compute_type="int8",
                download_root=MODELS_DIR,
                cpu_threads=CPU_THREADS,
            )
            segments, _info = model.transcribe(audio, vad_filter=True)
            text = " ".join(s.text.strip() for s in segments).strip()
        except Exception as e:  # try next candidate
            print(f"{model_id} failed: {e}", file=sys.stderr)
            continue
        if text:
            print(text)
            return 0
        print(f"empty transcription from {model_id}", file=sys.stderr)
    return 1


if __name__ == "__main__":
    sys.exit(main())
