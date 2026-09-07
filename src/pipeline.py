"""
pipeline.py — FaceID-Chain Verify  (orchestrator)

Three input modes:
  Webcam    →  python src/pipeline.py
  Image     →  python src/pipeline.py --image photo.jpg
  Clipboard →  python src/pipeline.py --clipboard

Optional:
  --threshold 0.60   (default 0.45 — higher = stricter match)
"""
import argparse
import contextlib
import io
import os
import sys
import time
from pathlib import Path

# Ensure src/ is importable
sys.path.insert(0, str(Path(__file__).parent))

import ui
from capture import capture_frame
from face_id import get_embedding, crop_face
from search import find_candidates
from verify_match import verify_candidates
from chain import submit_record, verify_record, demo_tamper


# ── Utility: run a function with stdout silenced ──────────────────────────────

def _quiet(fn, *args, **kwargs):
    """
    Call fn(*args, **kwargs) with stdout suppressed.
    Returns the function's return value.
    Any exception propagates normally after stdout is restored.
    """
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        return fn(*args, **kwargs)


# ── Main pipeline ─────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(
        description="FaceID-Chain Verify — Face → Web Search → Blockchain",
        add_help=True,
    )
    parser.add_argument(
        "--image", type=str, default=None,
        help="Path to a local image file (JPEG/PNG)."
    )
    parser.add_argument(
        "--clipboard", action="store_true",
        help="Read image from clipboard (paste a screenshot with Win+Shift+S first)."
    )
    parser.add_argument(
        "--threshold", type=float, default=0.45,
        help="Cosine-similarity threshold for accepting a face match (default: 0.45)."
    )
    parser.add_argument(
        "--fast", action="store_true",
        help="Fast mode: cap at 6 candidates (speeds up demo runs)."
    )
    args = parser.parse_args()

    ui.banner()

    # ── Stage 1 — Capture ────────────────────────────────────────────────────
    ui.step_running(1, "Capture")
    image_path: str = ""
    try:
        if args.clipboard:
            from PIL import ImageGrab  # pyrefly: ignore [missing-import]
            clip_img = ImageGrab.grabclipboard()
            if clip_img is None:
                raise ValueError(
                    "Clipboard is empty. "
                    "Take a screenshot (Win+Shift+S) then Ctrl+C the image."
                )
            os.makedirs("captured", exist_ok=True)
            image_path = f"captured/clipboard_{int(time.time())}.jpg"
            if clip_img.mode in ("RGBA", "P"):
                clip_img = clip_img.convert("RGB")
            clip_img.save(image_path, "JPEG", quality=95)
            ui.step_ok(1, "Capture", f"Clipboard → {image_path}")

        elif args.image:
            image_path = args.image
            if not os.path.exists(image_path):
                raise FileNotFoundError(f"File not found: {image_path}")
            ui.step_ok(1, "Capture", f"Image → {image_path}")

        else:
            # Webcam: must show the OpenCV window — do NOT silence this stage
            print()
            print(ui.dim(ui.gray("  ⬡  Webcam opened — press SPACE to capture, ESC to cancel.")))
            image_path = capture_frame()
            if not image_path or not os.path.exists(image_path):
                raise RuntimeError("No image captured. Press SPACE over the webcam window.")
            ui.step_ok(1, "Capture", f"Webcam → {image_path}")

    except Exception as exc:
        ui.step_fail(1, "Capture", str(exc))
        ui.failure_footer(1, str(exc))
        sys.exit(1)

    # ── Stage 2 — Face Detection & Embedding ─────────────────────────────────
    ui.step_running(2, "Face Detection & Embedding")
    try:
        emb_result = _quiet(get_embedding, image_path)
        if "error" in emb_result:
            raise ValueError(emb_result["error"])
        original_embedding: list[float] = emb_result["embedding"]
        ui.step_ok(
            2, "Face Detection & Embedding",
            f"512-d Facenet512 vector extracted"
        )
    except Exception as exc:
        ui.step_fail(2, "Face Detection & Embedding", str(exc))
        ui.failure_footer(2, str(exc))
        sys.exit(1)

    # ── Stage 2.5 — Face Crop (internal, no stage line) ──────────────────────
    facial_area    = emb_result.get("facial_area", {})
    search_path    = image_path
    crop_path: str | None = None
    if facial_area:
        try:
            crop_path  = _quiet(crop_face, image_path, facial_area, 0.40)
            if crop_path:
                search_path = crop_path
        except Exception:
            pass  # fall back to original image silently

    # ── Stage 3 — Reverse Image Search ───────────────────────────────────────
    ui.step_running(3, "Reverse Image Search")
    try:
        candidates: list[dict] = _quiet(find_candidates, search_path)
        if candidates is None:
            candidates = []
    except Exception as exc:
        candidates = []
        ui.step_fail(3, "Reverse Image Search", str(exc)[:80])
        ui.failure_footer(3, str(exc))
        sys.exit(1)
    finally:
        if crop_path and os.path.exists(crop_path):
            try:
                os.remove(crop_path)
            except OSError:
                pass

    if candidates:
        ui.step_ok(3, "Reverse Image Search",
                   f"{len(candidates)} social profile(s) discovered")
    else:
        ui.step_skip(3, "Reverse Image Search",
                     "No results — check APIFY_TOKEN and account credits")

    # ── Stage 4 — Face Match Verification ────────────────────────────────────
    ui.step_running(4, "Face Match Verification")
    verified: list[dict] = []
    if candidates:
        try:
            verified = _quiet(
                verify_candidates,
                original_embedding,
                candidates,
                args.threshold,
                6 if args.fast else 10,   # max_candidates
            )
            if verified is None:
                verified = []
        except Exception as exc:
            ui.step_fail(4, "Face Match Verification", str(exc)[:80])
            ui.failure_footer(4, str(exc))
            sys.exit(1)

    if verified:
        top_pct = verified[0]["similarity_score"] * 100
        ui.step_ok(
            4, "Face Match Verification",
            f"{len(verified)} match(es) confirmed — top {top_pct:.1f}%"
        )
    elif candidates:
        ui.step_skip(4, "Face Match Verification",
                     f"0/{len(candidates)} candidates passed threshold {args.threshold}")
    else:
        ui.step_skip(4, "Face Match Verification", "No candidates to verify")

    # Print the match results box (even if empty — shows the ⚠ message)
    ui.matches_box(verified)

    # ── Stage 5 — Blockchain Anchor ──────────────────────────────────────────
    ui.step_running(5, "Blockchain Anchor (Ethereum Sepolia)")
    best_url   = verified[0]["page_url"]        if verified else ""
    best_score = verified[0]["similarity_score"] if verified else 0.0
    evidence   = {
        "image_path":       os.path.basename(image_path),
        "best_match_url":   best_url,
        "similarity_score": best_score,
        "timestamp":        time.time(),
    }
    try:
        chain_record = _quiet(submit_record, evidence)
        if chain_record is None:
            raise RuntimeError("submit_record returned None")
        ui.step_ok(5, "Blockchain Anchor (Ethereum Sepolia)", "Transaction confirmed")
    except Exception as exc:
        ui.step_fail(5, "Blockchain Anchor (Ethereum Sepolia)", str(exc)[:80])
        ui.failure_footer(5, str(exc))
        sys.exit(1)

    ui.blockchain_box(chain_record)

    # ── Stage 6 — Tamper-Proof Demo ───────────────────────────────────────────
    ui.step_running(6, "Tamper-Proof Verification")
    try:
        data_hash_bytes = bytes.fromhex(chain_record["data_hash"])
        verify_status   = _quiet(verify_record, data_hash_bytes)
        _quiet(demo_tamper, evidence)
        exists = (verify_status or {}).get("exists", False)
        if exists:
            ui.step_ok(6, "Tamper-Proof Verification",
                       "Record on-chain ✓   Tamper detection active ✓")
        else:
            ui.step_fail(6, "Tamper-Proof Verification",
                         "verifyRecord returned exists=False — check contract")
    except Exception as exc:
        ui.step_fail(6, "Tamper-Proof Verification", str(exc)[:80])

    ui.success_footer()


if __name__ == "__main__":
    main()
