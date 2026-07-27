# services/video/analyzer.py
"""Local video analysis — the decomposed pipeline.

Turns a video file into a timestamped JSON digest that chat/Library/agents can
reason over, 100% locally:

    1. ffprobe metadata (duration, resolution, streams)
    2. keyframe extraction  — cv2 scene-change detection + a density floor
       (never longer than N seconds without a frame) + near-duplicate dedup,
       hard-capped so the single Metal GPU is never asked to caption hundreds
       of frames (prefill is the bottleneck on Apple Silicon, not RAM)
    3. timestamped transcript — faster-whisper via the existing STT service
       (CPU int8 → runs CONCURRENTLY with the GPU vision work, and PyAV pulls
       the audio track straight out of the MP4, no demux step)
    4. per-keyframe captioning via the existing vision model path
       (analyze_image_with_vl_result) WITH the transcript window around each
       frame injected into the prompt — measured ~+26% caption accuracy
    5. merge into a digest: {meta, transcript[], scenes[]} cached at
       data/uploads/.video/{file_id}.json (mirrors the .vision sidecar)

Jobs run in a background thread (a 1h video ≈ 20-30 min: STT on CPU overlaps
the ~seconds-per-frame GPU captioning). A module registry tracks progress and
supports cancel; best-effort registration with the Activity panel.
"""
from __future__ import annotations

import json
import logging
import os
import subprocess
import tempfile
import threading
import time
from typing import Any, Callable, Dict, List, Optional

logger = logging.getLogger(__name__)

# ── Tunables (owned in-tree; derived from the claude-real-video /
#    video-caption ablation recipes) ─────────────────────────────────────────
SCENE_DIFF_THRESHOLD = 0.30      # mean abs pixel diff (normalized) → new scene
DENSITY_FLOOR_SEC = 20.0         # never go longer than this without a frame
DEDUP_DIFF_MIN = 0.08            # skip frame if <8% different from last kept
MAX_FRAMES = 60                  # hard GPU budget per video
SAMPLE_STRIDE_SEC = 1.0          # how often we LOOK at frames (not keep)
TRANSCRIPT_WINDOW_SEC = 25.0     # transcript context injected per frame
DIGEST_DIRNAME = ".video"
MAX_INJECT_CHARS = 24000         # cap on digest text injected into chat

_FFPROBE = "/opt/homebrew/bin/ffprobe"
if not os.path.exists(_FFPROBE):
    _FFPROBE = "ffprobe"  # PATH fallback

VIDEO_EXTENSIONS = {".mp4", ".mov", ".webm", ".mkv", ".avi", ".m4v"}

# ── Job registry ─────────────────────────────────────────────────────────────
_jobs: Dict[str, Dict[str, Any]] = {}
_jobs_lock = threading.Lock()


def job_status(file_id: str) -> Optional[Dict[str, Any]]:
    with _jobs_lock:
        j = _jobs.get(file_id)
        return dict(j) if j else None


def _set(file_id: str, **kw) -> None:
    with _jobs_lock:
        _jobs.setdefault(file_id, {}).update(kw)


def cancel_job(file_id: str) -> bool:
    with _jobs_lock:
        j = _jobs.get(file_id)
    if j and j.get("status") not in ("done", "error", "cancelled"):
        j["_cancel"].set()
        return True
    return False


# ── Digest sidecar ───────────────────────────────────────────────────────────

def digest_path(upload_root: str, file_id: str) -> str:
    d = os.path.join(upload_root, DIGEST_DIRNAME)
    os.makedirs(d, exist_ok=True)
    return os.path.join(d, file_id + ".json")


def load_digest(upload_root: str, file_id: str) -> Optional[Dict[str, Any]]:
    p = digest_path(upload_root, file_id)
    if not os.path.isfile(p):
        return None
    try:
        with open(p, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return None


# ── Helpers ──────────────────────────────────────────────────────────────────

def _mmss(t: float) -> str:
    t = int(t)
    if t >= 3600:
        return f"{t // 3600}:{(t % 3600) // 60:02d}:{t % 60:02d}"
    return f"{t // 60:02d}:{t % 60:02d}"


def probe(path: str) -> Dict[str, Any]:
    """ffprobe → {duration, width, height, has_audio}."""
    try:
        out = subprocess.run(
            [_FFPROBE, "-v", "quiet", "-print_format", "json",
             "-show_format", "-show_streams", path],
            capture_output=True, text=True, timeout=30,
        )
        info = json.loads(out.stdout or "{}")
        dur = float(info.get("format", {}).get("duration", 0) or 0)
        w = h = 0
        has_audio = False
        for s in info.get("streams", []):
            if s.get("codec_type") == "video" and not w:
                w, h = int(s.get("width", 0) or 0), int(s.get("height", 0) or 0)
            if s.get("codec_type") == "audio":
                has_audio = True
        return {"duration": dur, "width": w, "height": h, "has_audio": has_audio}
    except Exception as e:
        logger.warning("ffprobe failed for %s: %s", path, e)
        return {"duration": 0, "width": 0, "height": 0, "has_audio": True}


def extract_keyframes(path: str, out_dir: str,
                      max_frames: int = MAX_FRAMES,
                      cancel: Optional[threading.Event] = None) -> List[Dict[str, Any]]:
    """Scene-aware keyframe extraction with a density floor and dedup.

    Returns [{"t": seconds, "path": jpg}] sorted by time.
    """
    import cv2  # opencv is already in the venv
    import numpy as np

    cap = cv2.VideoCapture(path)
    if not cap.isOpened():
        raise RuntimeError("could not open video")
    fps = cap.get(cv2.CAP_PROP_FPS) or 25.0
    total = int(cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0)
    duration = total / fps if fps else 0
    stride = max(1, int(round(fps * SAMPLE_STRIDE_SEC)))
    # Adaptive density floor: short clips still deserve several frames
    # (duration/8 → ~8 frames minimum coverage), long ones keep the cap sane.
    density_floor = min(DENSITY_FLOOR_SEC, max(2.0, duration / 8.0)) if duration else DENSITY_FLOOR_SEC

    kept: List[Dict[str, Any]] = []
    last_small = None
    last_kept_t = -1e9
    os.makedirs(out_dir, exist_ok=True)

    idx = 0
    while True:
        if cancel is not None and cancel.is_set():
            break
        ok = cap.grab()
        if not ok:
            break
        if idx % stride:
            idx += 1
            continue
        ok, frame = cap.retrieve()
        idx += 1
        if not ok or frame is None:
            continue
        t = (idx - 1) / fps
        # Downscale to a small COLOR thumb for cheap diffing. Color (not gray)
        # matters: a red→green slide swap at similar luminance is a real scene
        # change that grayscale diffing misses entirely.
        small = cv2.resize(frame, (64, 36)).astype("float32") / 255.0
        keep = False
        if last_small is None:
            keep = True
        else:
            diff = float(np.mean(np.abs(small - last_small)))
            if diff >= SCENE_DIFF_THRESHOLD:
                keep = True                      # scene change
            elif (t - last_kept_t) >= density_floor and diff >= DEDUP_DIFF_MIN:
                keep = True                      # density floor (and not a dupe)
        if keep:
            jpg = os.path.join(out_dir, f"f{int(t * 1000):09d}.jpg")
            cv2.imwrite(jpg, frame, [int(cv2.IMWRITE_JPEG_QUALITY), 82])
            kept.append({"t": round(t, 2), "path": jpg})
            last_small = small
            last_kept_t = t
    cap.release()

    # Enforce the GPU budget: thin evenly if over.
    if len(kept) > max_frames:
        step = len(kept) / max_frames
        kept = [kept[int(i * step)] for i in range(max_frames)]
    logger.info("keyframes: kept %d frames over %.0fs", len(kept), duration)
    return kept


def _transcript_window(segments: List[Dict[str, Any]], t: float,
                       window: float = TRANSCRIPT_WINDOW_SEC) -> str:
    parts = [s["text"].strip() for s in segments
             if s["start"] <= t + window and s["end"] >= t - window]
    return " ".join(parts).strip()


def _caption_prompt(t: float, transcript_ctx: str) -> str:
    p = (f"This is a frame from a video at timestamp {_mmss(t)}. "
         "Describe it concisely and concretely: setting, people/objects, any "
         "readable on-screen text (slides, UI, captions), and what action is "
         "happening. 2-4 sentences, no speculation.")
    if transcript_ctx:
        p += ("\n\nWhat is being SAID around this moment (from the audio "
              f"transcript, for context): \"{transcript_ctx[:600]}\"")
    return p


# ── The pipeline ─────────────────────────────────────────────────────────────

def analyze_video(path: str, file_id: str, upload_root: str,
                  progress: Optional[Callable[[str, float], None]] = None,
                  cancel: Optional[threading.Event] = None) -> Dict[str, Any]:
    """Run the full decomposed pipeline. Blocking — call from a worker thread."""
    def report(stage: str, frac: float):
        if progress:
            progress(stage, frac)

    t0 = time.time()
    meta = probe(path)
    report("probing", 0.02)

    # ── Transcript on CPU, concurrently with GPU work ──
    segments: List[Dict[str, Any]] = []
    stt_err: List[str] = []

    def _stt():
        try:
            from services.stt.stt_service import get_stt_service
            svc = get_stt_service()
            segs = svc.transcribe_segments(path)
            if segs:
                segments.extend(segs)
        except Exception as e:  # noqa: BLE001
            stt_err.append(str(e))
            logger.warning("video STT failed: %s", e)

    stt_thread = None
    if meta.get("has_audio", True):
        stt_thread = threading.Thread(target=_stt, name=f"video-stt-{file_id[:8]}", daemon=True)
        stt_thread.start()

    # ── Keyframes ──
    report("extracting frames", 0.05)
    frames_dir = os.path.join(tempfile.gettempdir(), f"paios-video-{file_id}")
    frames = extract_keyframes(path, frames_dir, cancel=cancel)
    if cancel is not None and cancel.is_set():
        raise InterruptedError("cancelled")

    # Wait for the transcript BEFORE captioning — the transcript window in the
    # vision prompt is the single biggest caption-quality lever (+26%).
    if stt_thread is not None:
        report("transcribing", 0.15)
        stt_thread.join(timeout=3600)

    # ── Caption frames (GPU, sequential — single Metal GPU) ──
    from src.document_processor import analyze_image_with_vl_result
    scenes: List[Dict[str, Any]] = []
    n = max(1, len(frames))
    for i, fr in enumerate(frames):
        if cancel is not None and cancel.is_set():
            raise InterruptedError("cancelled")
        report(f"captioning frame {i + 1}/{n}", 0.2 + 0.75 * (i / n))
        ctx = _transcript_window(segments, fr["t"])
        res = analyze_image_with_vl_result(fr["path"], prompt=_caption_prompt(fr["t"], ctx))
        cap_text = (res.get("text") or "").strip()
        if cap_text and not cap_text.startswith("["):
            scenes.append({"t": fr["t"], "caption": cap_text})

    # ── Merge + persist ──
    report("merging", 0.97)
    digest = {
        "file_id": file_id,
        "meta": {**meta, "analyzed_at": time.time(),
                 "frames_captioned": len(scenes),
                 "elapsed_sec": round(time.time() - t0, 1),
                 "stt_error": (stt_err[0] if stt_err else None)},
        "transcript": segments,
        "scenes": scenes,
    }
    with open(digest_path(upload_root, file_id), "w", encoding="utf-8") as f:
        json.dump(digest, f, ensure_ascii=False, indent=1)

    # Clean the temp frames
    try:
        for fr in frames:
            os.unlink(fr["path"])
        os.rmdir(frames_dir)
    except Exception:
        pass

    report("done", 1.0)
    logger.info("video digest for %s: %d segs, %d scenes in %.0fs",
                file_id, len(segments), len(scenes), time.time() - t0)
    return digest


# ── Background job wrapper ───────────────────────────────────────────────────

def start_analysis(path: str, file_id: str, upload_root: str,
                   owner: Optional[str] = None, force: bool = False) -> Dict[str, Any]:
    """Kick a background analysis (idempotent). Returns the job status."""
    existing = load_digest(upload_root, file_id)
    if existing and not force:
        return {"status": "done", "cached": True}
    st = job_status(file_id)
    if st and st.get("status") not in ("done", "error", "cancelled"):
        return {k: v for k, v in st.items() if not k.startswith("_")}

    cancel = threading.Event()
    _set(file_id, status="queued", stage="queued", progress=0.0,
         started=time.time(), error=None, _cancel=cancel)

    # Best-effort Activity-panel registration (universal stop).
    act_id = None
    try:
        from services import activity
        act_id = activity.register(kind="video", model="qwen2.5vl",
                                   label=f"Video analysis {file_id[:8]}",
                                   cancel=lambda: cancel.set())
    except Exception:
        pass

    def _run():
        _set(file_id, status="running")
        try:
            analyze_video(path, file_id, upload_root,
                          progress=lambda s, f: _set(file_id, stage=s, progress=round(f, 3)),
                          cancel=cancel)
            _set(file_id, status="done", progress=1.0, stage="done")
        except InterruptedError:
            _set(file_id, status="cancelled", stage="cancelled")
        except Exception as e:  # noqa: BLE001
            logger.error("video analysis failed for %s: %s", file_id, e, exc_info=True)
            _set(file_id, status="error", error=str(e)[:500])
        finally:
            if act_id is not None:
                try:
                    from services import activity
                    activity.unregister(act_id)
                except Exception:
                    pass

    threading.Thread(target=_run, name=f"video-analyze-{file_id[:8]}", daemon=True).start()
    return {"status": "queued"}


# ── Chat injection text ──────────────────────────────────────────────────────

def digest_to_text(digest: Dict[str, Any], max_chars: int = MAX_INJECT_CHARS) -> str:
    """Render the digest as compact timestamped text for LLM context."""
    meta = digest.get("meta", {})
    lines = [f"[VIDEO DIGEST — duration {_mmss(meta.get('duration', 0))}, "
             f"{len(digest.get('scenes', []))} visual scenes, "
             f"{len(digest.get('transcript', []))} speech segments]"]

    scenes = digest.get("scenes", [])
    if scenes:
        lines.append("\n== VISUAL TIMELINE ==")
        for s in scenes:
            lines.append(f"[{_mmss(s['t'])}] {s['caption']}")

    trans = digest.get("transcript", [])
    if trans:
        lines.append("\n== TRANSCRIPT ==")
        # Merge segments into ~45s blocks to stay compact
        block, block_start, block_end = [], None, 0
        for seg in trans:
            if block_start is None:
                block_start = seg["start"]
            block.append(seg["text"].strip())
            block_end = seg["end"]
            if block_end - block_start >= 45:
                lines.append(f"[{_mmss(block_start)}–{_mmss(block_end)}] " + " ".join(block))
                block, block_start = [], None
        if block:
            lines.append(f"[{_mmss(block_start)}–{_mmss(block_end)}] " + " ".join(block))

    text = "\n".join(lines)
    if len(text) > max_chars:
        text = text[:max_chars] + "\n[…digest truncated…]"
    return text
