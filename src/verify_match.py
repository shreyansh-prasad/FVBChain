import os
import sys
import tempfile
import requests
import re

# Import CV layer — do not duplicate its logic
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from face_id import get_embedding


def _cosine_similarity(vec_a: list[float], vec_b: list[float]) -> float:
    """Computes cosine similarity between two equal-length vectors."""
    dot = sum(a * b for a, b in zip(vec_a, vec_b))
    norm_a = sum(a * a for a in vec_a) ** 0.5
    norm_b = sum(b * b for b in vec_b) ** 0.5
    if norm_a == 0.0 or norm_b == 0.0:
        return 0.0
    return dot / (norm_a * norm_b)


def _download_image(url: str) -> str | None:
    """
    Downloads an image from url to a temp file.
    Returns the temp file path, or None on failure.
    """
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36"
    }
    try:
        # If url is a webpage (not a direct image), extract the og:image meta tag
        if not url.lower().split("?")[0].endswith(('.png', '.jpg', '.jpeg', '.webp', '.gif')):
            page = requests.get(url, timeout=15, headers=headers)
            # Use regex to find og:image content without needing BeautifulSoup
            match = re.search(
                r'<meta[^>]+property=["\']og:image["\'][^>]+content=["\']([^"\']+)["\']',
                page.text
            ) or re.search(
                r'<meta[^>]+content=["\']([^"\']+)["\'][^>]+property=["\']og:image["\']',
                page.text
            )
            if match:
                og_url = match.group(1).strip()
                print(f"[STAGE] verify:   -> og:image extracted: {og_url[:80]}")
                url = og_url
            else:
                print(f"[STAGE] verify:   -> No og:image found, using original URL.")

        response = requests.get(url, timeout=30, stream=True, headers=headers)
        response.raise_for_status()
        suffix = ".jpg"
        with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
            for chunk in response.iter_content(chunk_size=8192):
                tmp.write(chunk)
            return tmp.name
    except Exception as e:
        print(f"[STAGE] verify: Failed to download {url} — {type(e).__name__}: {e}")
        return None


def verify_candidates(
    original_embedding: list[float],
    candidates: list[dict],
    threshold: float = 0.45,
) -> list[dict]:
    """
    For each candidate, downloads its image, re-embeds it, and computes
    cosine similarity against original_embedding.
    Prints every score — accepted or not.
    Returns only candidates scoring >= threshold, sorted descending by score.
    """
    if not candidates:
        print("[STAGE] verify: No candidates to verify.")
        return []

    print(f"[STAGE] verify: Verifying {len(candidates)} candidate(s) at threshold={threshold}")

    accepted: list[dict] = []

    for i, candidate in enumerate(candidates):
        page_url = candidate.get("page_url", "")
        image_url = candidate.get("image_url", "")
        print(f"\n[STAGE] verify: [{i + 1}/{len(candidates)}] {page_url}")

        if not image_url and not page_url:
            print(f"[STAGE] verify:   -> No image_url or page_url — skipping.")
            continue

        # Download candidate image (try page_url if image_url is missing)
        target_url = image_url if image_url else page_url
        tmp_path = _download_image(target_url)
        if tmp_path is None:
            print(f"[STAGE] verify:   -> Download failed — skipping.")
            continue

        # Re-embed with same model/backend as original
        embedding_result = get_embedding(tmp_path)

        # Clean up temp file
        try:
            os.remove(tmp_path)
        except OSError:
            pass

        if "error" in embedding_result:
            print(f"[STAGE] verify:   -> No face detected — skipping.")
            continue

        cand_embedding = embedding_result.get("embedding", [])
        if len(cand_embedding) != len(original_embedding):
            print(
                f"[STAGE] verify:   -> Embedding length mismatch "
                f"({len(cand_embedding)} vs {len(original_embedding)}) — skipping."
            )
            continue

        score = _cosine_similarity(original_embedding, cand_embedding)
        verdict = "ACCEPTED" if score >= threshold else "REJECTED"
        print(f"[STAGE] verify:   -> Score: {score:.4f} [{verdict}]")

        if score >= threshold:
            accepted.append({**candidate, "similarity_score": round(score, 4)})

    # Sort accepted by score descending
    accepted.sort(key=lambda x: x["similarity_score"], reverse=True)
    print(f"\n[STAGE] verify: {len(accepted)} candidate(s) accepted above threshold {threshold}.")
    return accepted


if __name__ == "__main__":
    # Standalone test: expects a local image path as argument.
    # Will produce a dummy embedding to verify the comparison logic runs.
    if len(sys.argv) > 1:
        test_path = sys.argv[1]
        print(f"[STAGE] verify: Standalone test on {test_path}")
        result = get_embedding(test_path)
        if "error" in result:
            print(f"[STAGE] verify: Could not embed test image — {result}")
            sys.exit(1)
        original_emb = result["embedding"]
        print(f"[STAGE] verify: Original embedding length: {len(original_emb)}")
        # Self-verify: the same image should score 1.0
        dummy_candidates = [{"page_url": "self-test", "image_url": "", "source": "local"}]
        score = _cosine_similarity(original_emb, original_emb)
        print(f"[STAGE] verify: Self-similarity score: {score:.4f} (expect 1.0)")
    else:
        print("[STAGE] verify: Pass an image path to run a self-similarity test.")
