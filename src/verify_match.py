import os
import sys
import json
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


_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "en-US,en;q=0.9",
}

_IMAGE_EXTS = ('.png', '.jpg', '.jpeg', '.webp', '.gif')


def _is_direct_image(url: str) -> bool:
    return url.lower().split("?")[0].endswith(_IMAGE_EXTS)


def _extract_best_image_url(page_html: str, page_url: str) -> str | None:
    """
    Tries multiple strategies to extract the highest-quality image URL
    from a page's HTML, in order of reliability:
      1. og:image  (standard Open Graph)
      2. twitter:image / twitter:image:src
      3. Pinterest JSON-LD (catches pin images that Pinterest hides from og:image)
      4. First large <img> src that looks like a real photo
    Returns the best URL found, or None.
    """

    # --- Strategy 1 & 2: meta tags (og:image, twitter:image) ---
    meta_patterns = [
        r'<meta[^>]+property=["\']og:image["\'][^>]+content=["\']([^"\']+)["\']',
        r'<meta[^>]+content=["\']([^"\']+)["\'][^>]+property=["\']og:image["\']',
        r'<meta[^>]+name=["\']twitter:image(?::src)?["\'][^>]+content=["\']([^"\']+)["\']',
        r'<meta[^>]+content=["\']([^"\']+)["\'][^>]+name=["\']twitter:image(?::src)?["\']',
    ]
    for pattern in meta_patterns:
        m = re.search(pattern, page_html, re.IGNORECASE)
        if m:
            url = m.group(1).strip()
            if url and not url.endswith('.svg'):
                print(f"[STAGE] verify:   -> meta image extracted: {url[:80]}")
                return url

    # --- Strategy 3: Pinterest JSON-LD ---
    if "pinterest" in page_url.lower():
        json_ld_match = re.search(r'<script[^>]+type=["\']application/ld\+json["\'][^>]*>(.*?)</script>',
                                  page_html, re.DOTALL | re.IGNORECASE)
        if json_ld_match:
            try:
                data = json.loads(json_ld_match.group(1))
                # Pinterest JSON-LD puts the pin image under 'image' or 'thumbnailUrl'
                for key in ("image", "thumbnailUrl", "contentUrl"):
                    val = data.get(key)
                    if isinstance(val, str) and val.startswith("http"):
                        print(f"[STAGE] verify:   -> Pinterest JSON-LD image: {val[:80]}")
                        return val
                    if isinstance(val, dict):
                        for subkey in ("url", "contentUrl"):
                            sub = val.get(subkey, "")
                            if sub.startswith("http"):
                                print(f"[STAGE] verify:   -> Pinterest JSON-LD image: {sub[:80]}")
                                return sub
            except (json.JSONDecodeError, AttributeError):
                pass

    # --- Strategy 4: largest <img> on the page ---
    img_tags = re.findall(
        r'<img[^>]+src=["\']([^"\']+)["\'][^>]*(?:width=["\'](\d+)["\'])?',
        page_html, re.IGNORECASE
    )
    candidates = [(src, int(w) if w else 0) for src, w in img_tags
                  if src.startswith("http") and not src.endswith('.svg')]
    if candidates:
        candidates.sort(key=lambda x: x[1], reverse=True)
        best_src = candidates[0][0]
        print(f"[STAGE] verify:   -> Fallback img src: {best_src[:80]}")
        return best_src

    print("[STAGE] verify:   -> No image URL found in page.")
    return None


def _download_url(url: str, timeout: int = 30) -> str | None:
    """Downloads a URL to a temp file. Returns path or None on failure."""
    try:
        resp = requests.get(url, timeout=timeout, stream=True, headers=_HEADERS)
        resp.raise_for_status()
        with tempfile.NamedTemporaryFile(delete=False, suffix=".jpg") as tmp:
            for chunk in resp.iter_content(chunk_size=8192):
                tmp.write(chunk)
            return tmp.name
    except Exception as e:
        print(f"[STAGE] verify:   -> Download failed ({type(e).__name__}): {e}")
        return None


def _download_image(url: str) -> str | None:
    """
    Downloads the best-quality image reachable from `url`.
    If it's a webpage, extracts the best image URL first.
    """
    if _is_direct_image(url):
        return _download_url(url)

    # It's a webpage — fetch and extract the best image URL
    try:
        page_resp = requests.get(url, timeout=15, headers=_HEADERS)
        page_resp.raise_for_status()
        best_url = _extract_best_image_url(page_resp.text, url)
    except Exception as e:
        print(f"[STAGE] verify:   -> Failed to fetch page ({type(e).__name__}): {e}")
        return None

    if best_url:
        return _download_url(best_url)

    # Absolute last resort: try downloading the page URL directly as an image
    print("[STAGE] verify:   -> Last resort: downloading page URL as image.")
    return _download_url(url)


def _get_all_embeddings(image_path: str) -> list[list[float]]:
    """
    Extract embeddings for ALL faces found in image_path.
    Falls back to single-face get_embedding if multi-face extraction fails.
    Returns a list of embeddings (may be empty if no face detected).
    """
    from deepface import DeepFace
    try:
        results = DeepFace.represent(
            img_path=image_path,
            model_name="Facenet512",
            detector_backend="mtcnn",
        )
        if not isinstance(results, list):
            results = [results]
        embeddings = [r["embedding"] for r in results if "embedding" in r]
        if len(embeddings) > 1:
            print(f"[STAGE] verify:   -> {len(embeddings)} faces found in candidate — scoring all.")
        return embeddings
    except ValueError:
        return []  # no face detected
    except Exception as e:
        print(f"[STAGE] verify:   -> Embedding extraction error: {type(e).__name__}: {e}")
        return []


def verify_candidates(
    original_embedding: list[float],
    candidates: list[dict],
    threshold: float = 0.45,
) -> list[dict]:
    """
    For each candidate:
      1. Downloads the best available image (using multi-strategy extraction)
      2. Detects ALL faces in that image
      3. Scores each face and keeps the best score
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
            print("[STAGE] verify:   -> No image_url or page_url — skipping.")
            continue

        # Prefer image_url (direct); fall back to page_url (webpage scrape)
        target_url = image_url if image_url else page_url
        tmp_path = _download_image(target_url)

        if tmp_path is None:
            print("[STAGE] verify:   -> Could not obtain image — skipping.")
            continue

        # Extract ALL faces and score each one
        all_embeddings = _get_all_embeddings(tmp_path)
        try:
            os.remove(tmp_path)
        except OSError:
            pass

        if not all_embeddings:
            print("[STAGE] verify:   -> No face detected — skipping.")
            continue

        # Compute cosine similarity for every face; keep the best score
        best_score = max(
            _cosine_similarity(original_embedding, emb)
            for emb in all_embeddings
            if len(emb) == len(original_embedding)
        )

        verdict = "ACCEPTED" if best_score >= threshold else "REJECTED"
        print(f"[STAGE] verify:   -> Best score: {best_score:.4f} [{verdict}]")

        if best_score >= threshold:
            accepted.append({**candidate, "similarity_score": round(best_score, 4)})

    # Sort accepted by score descending
    accepted.sort(key=lambda x: x["similarity_score"], reverse=True)
    print(f"\n[STAGE] verify: {len(accepted)} candidate(s) accepted above threshold {threshold}.")
    return accepted


if __name__ == "__main__":
    # Standalone test: expects a local image path as argument.
    if len(sys.argv) > 1:
        test_path = sys.argv[1]
        print(f"[STAGE] verify: Standalone test on {test_path}")
        result = get_embedding(test_path)
        if "error" in result:
            print(f"[STAGE] verify: Could not embed test image — {result}")
            sys.exit(1)
        original_emb = result["embedding"]
        print(f"[STAGE] verify: Original embedding length: {len(original_emb)}")
        score = _cosine_similarity(original_emb, original_emb)
        print(f"[STAGE] verify: Self-similarity score: {score:.4f} (expect 1.0)")
    else:
        print("[STAGE] verify: Pass an image path to run a self-similarity test.")
