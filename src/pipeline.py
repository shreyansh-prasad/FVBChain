import argparse
import os
import sys
import time
from pathlib import Path

# Ensure we can import from src/
sys.path.insert(0, str(Path(__file__).parent))

from capture import capture_frame
from face_id import get_embedding, crop_face
from search import find_candidates
from verify_match import verify_candidates
from chain import submit_record, verify_record, demo_tamper


def main():
    parser = argparse.ArgumentParser(description="FaceID Chain Verification Pipeline")
    parser.add_argument("--image", type=str, default=None, help="Path to input image")
    parser.add_argument("--clipboard", action="store_true", help="Read image from clipboard (paste a screenshot)")
    parser.add_argument("--threshold", type=float, default=0.45, help="Similarity threshold")
    args = parser.parse_args()

    print("=" * 70)
    print("[PIPELINE] Starting FaceID-Chain Verification Pipeline")
    print("=" * 70)

    # ── STAGE 1: Capture ────────────────────────────────────────────────────────
    print("\n[STAGE 1] Capture Frame")
    try:
        if args.clipboard:
            print("[STAGE 1] Reading image from clipboard...")
            try:
                from PIL import ImageGrab
                import time as _time
                clip_img = ImageGrab.grabclipboard()
                if clip_img is None:
                    raise ValueError(
                        "Clipboard is empty or does not contain an image. "
                        "Copy an image first (e.g. Win+Shift+S screenshot or Ctrl+C on a photo)."
                    )
                os.makedirs("captured", exist_ok=True)
                image_path = f"captured/clipboard_{int(_time.time())}.jpg"
                # Convert RGBA -> RGB so JPEG save works
                if clip_img.mode in ("RGBA", "P"):
                    clip_img = clip_img.convert("RGB")
                clip_img.save(image_path, "JPEG", quality=95)
                print(f"[STAGE 1] Clipboard image saved to: {image_path}")
            except ImportError:
                raise RuntimeError("Pillow not installed — run: pip install Pillow")
        elif args.image:
            image_path = args.image
            print(f"[STAGE 1] Using provided image: {image_path}")
        else:
            print("[STAGE 1] Launching webcam... (Press SPACE to capture)")
            image_path = capture_frame()
            print(f"[STAGE 1] Captured image saved to: {image_path}")

        if not os.path.exists(image_path):
            raise FileNotFoundError(f"Image not found at {image_path}")
    except Exception as e:
        print(f"[STAGE 1] FAILED: {type(e).__name__} - {e}")
        sys.exit(1)

    # ── STAGE 2: Embedding ──────────────────────────────────────────────────────
    print("\n[STAGE 2] Face Extraction & Embedding")
    try:
        emb_result = get_embedding(image_path)
        if "error" in emb_result:
            raise ValueError(f"Face extraction failed: {emb_result['error']}")
        
        original_embedding = emb_result["embedding"]
        print(f"[STAGE 2] SUCCESS - Embedding generated (Length: {len(original_embedding)})")
    except Exception as e:
        print(f"[STAGE 2] FAILED: {type(e).__name__} - {e}")
        sys.exit(1)

    # ── STAGE 2.5: Face Crop for Search ─────────────────────────────────────────
    # Upload a tight face crop to Yandex rather than the raw screenshot.
    # This removes background noise (LinkedIn header, page chrome, etc.)
    # and gives Yandex the best possible signal to find matching profiles.
    facial_area = emb_result.get("facial_area", {})
    search_image_path = image_path  # fallback: use original if crop fails
    crop_path: str | None = None
    if facial_area:
        crop_path = crop_face(image_path, facial_area, padding=0.40)
        if crop_path:
            search_image_path = crop_path
            print(f"[PIPELINE] Using face crop for Yandex search: {search_image_path}")
        else:
            print("[PIPELINE] Face crop failed — using original image for Yandex search.")
    else:
        print("[PIPELINE] No facial_area returned — using original image for Yandex search.")

    # ── STAGE 3: Reverse-Image Search ───────────────────────────────────────────
    print("\n[STAGE 3] Reverse Image Search (Social Media)")
    try:
        candidates = find_candidates(search_image_path)
        print(f"[STAGE 3] SUCCESS - Found {len(candidates)} candidate(s)")
    except Exception as e:
        print(f"[STAGE 3] FAILED: {type(e).__name__} - {e}")
        sys.exit(1)
    finally:
        # Clean up temp crop file
        if crop_path and os.path.exists(crop_path):
            try:
                os.remove(crop_path)
            except OSError:
                pass

    # ── STAGE 4: Similarity Verification ────────────────────────────────────────
    print("\n[STAGE 4] Candidate Verification")
    try:
        verified_matches = []
        if candidates:
            verified_matches = verify_candidates(original_embedding, candidates, args.threshold)
            print(f"[STAGE 4] SUCCESS - {len(verified_matches)} candidate(s) met threshold {args.threshold}")
        else:
            print("[STAGE 4] SUCCESS - No candidates to verify.")
    except Exception as e:
        print(f"[STAGE 4] FAILED: {type(e).__name__} - {e}")
        sys.exit(1)

    # ── STAGE 5: Blockchain Submission ──────────────────────────────────────────
    print("\n[STAGE 5] Submit Evidence On-Chain (Sepolia)")
    try:
        # Build evidence dict as requested
        best_match_url = verified_matches[0]["page_url"] if verified_matches else ""
        best_score = verified_matches[0]["similarity_score"] if verified_matches else 0.0
        
        evidence = {
            "image_path": os.path.basename(image_path),
            "best_match_url": best_match_url,
            "similarity_score": best_score,
            "timestamp": time.time(),
        }
        
        print(f"[STAGE 5] Evidence payload: {evidence}")
        chain_record = submit_record(evidence)
        print(f"[STAGE 5] SUCCESS - Tx Hash: {chain_record['tx_hash']}")
        print(f"[STAGE 5] SUCCESS - Explorer: {chain_record['explorer_url']}")
        print(f"[STAGE 5] SUCCESS - IPFS CID: {chain_record['cid']}")
    except Exception as e:
        print(f"[STAGE 5] FAILED: {type(e).__name__} - {e}")
        sys.exit(1)

    # ── STAGE 6: On-Chain Verification & Tamper Demo ────────────────────────────
    print("\n[STAGE 6] On-Chain Verification & Tamper Demo")
    try:
        data_hash_bytes = bytes.fromhex(chain_record["data_hash"])
        verify_status = verify_record(data_hash_bytes)
        print(f"[STAGE 6] SUCCESS - On-chain record exists: {verify_status['exists']}")
        
        # Run Tamper Demo
        demo_tamper(evidence)
    except Exception as e:
        print(f"[STAGE 6] FAILED: {type(e).__name__} - {e}")
        sys.exit(1)

    print("\n" + "=" * 70)
    print("[PIPELINE] SUCCESS - All stages completed.")
    print("=" * 70)


if __name__ == "__main__":
    main()
