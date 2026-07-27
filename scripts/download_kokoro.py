#!/usr/bin/env python3
"""Download the Kokoro-82M ONNX model + voices for local TTS (kokoro-onnx).

Files (~340 MB total) go to data/models/kokoro/ (override with PAIOS_KOKORO_DIR).
Open-source model: hexgrad/Kokoro-82M, ONNX build by thewh1teagle/kokoro-onnx.
"""
import os
import sys
import urllib.request

DIR = os.environ.get("PAIOS_KOKORO_DIR", "data/models/kokoro")
BASE = "https://github.com/thewh1teagle/kokoro-onnx/releases/download/model-files-v1.0"
FILES = {
    "kokoro-v1.0.onnx": f"{BASE}/kokoro-v1.0.onnx",
    "voices-v1.0.bin": f"{BASE}/voices-v1.0.bin",
}


def _fetch(url: str, dest: str):
    def _hook(blocks, bs, total):
        done = blocks * bs
        pct = (done / total * 100) if total > 0 else 0
        sys.stdout.write(f"\r  {os.path.basename(dest)}: {done // (1024*1024)}MB ({pct:.0f}%)")
        sys.stdout.flush()
    urllib.request.urlretrieve(url, dest, _hook)
    print()


def main():
    os.makedirs(DIR, exist_ok=True)
    for name, url in FILES.items():
        dest = os.path.join(DIR, name)
        if os.path.exists(dest) and os.path.getsize(dest) > 1_000_000:
            print(f"  {name}: already present ({os.path.getsize(dest)//(1024*1024)}MB) — skip")
            continue
        print(f"Downloading {name} …")
        _fetch(url, dest)
    print("Kokoro model ready in", DIR)


if __name__ == "__main__":
    main()
