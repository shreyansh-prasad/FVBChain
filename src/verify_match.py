import os
import sys
import json
import tempfile
import requests
import re
from concurrent.futures import ThreadPoolExecutor, as_completed

# Import CV layer — do not duplicate its logic
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from face_id import get_embedding

# ---------------------------------------------------------------------------
# HTTP helpers
# ---------------------------------------------------------------------------

_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "en-US,en;q=0.9",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
}

_IMAGE_EXTS = ('.png', '.jpg', '.jpeg', '.webp', '.gif')
_MIN_FACE_PX = 80  # reject images too small to embed accurately


def _is_direct_image(url: str) -> bool:
    return url.lower().split("?")[0].endswith(_IMAGE_EXTS)


# ---------------------------------------------------------------------------
# Cosine similarity
# ---------------------------------------------------------------------------

def _cosine_similarity(vec_a: list[float], vec_b: list[float]) -> float:
    """Computes cosine similarity between two equal-length vectors."""
    dot = sum(a * b for a, b in zip(vec_a, vec_b))
    norm_a = sum(a * a for a in vec_a) ** 0.5
    norm_b = sum(b * b for b in vec_b) ** 0.5
    if norm_a == 0.0 or norm_b == 0.0:
        return 0.0
    return dot / (norm_a * norm_b)


# ---------------------------------------------------------------------------
# Platform-specific: Pinterest
# ---------------------------------------------------------------------------

def _upgrade_pinterest_url(url: str) -> str:
    """
    Pinterest CDN serves multiple resolutions via path segment:
        /236x/  → thumbnail  (~236px wide)
        /564x/  → medium     (~564px wide)
        /736x/  → large      (~736px wide)
        /originals/ → full resolution
    Rewrite any CDN URL to 'originals' for maximum resolution.
    """
    # pinimg.com is Pinterest's CDN
    if "pinimg.com" not in url:
        return url
    upgraded = re.sub(
        r"(pinimg\.com/)\d+x(?:/\w+)?/",
        r"\1originals/",
        url
    )
    if upgraded != url:
        print(f"[STAGE] verify:   -> Pinterest URL upgraded to originals: {upgraded[:80]}")
    return upgraded


def _extract_pinterest_best_image(page_html: str) -> str | None:
    """
    Pinterest buries the full-res image URL inside a JSON blob assigned to
    window.__PWS_DATA__ or window.__INITIAL_STATE__. Parsing it gives us the
    'orig' image URL which is always the full resolution.
    Falls back to og:image if the JSON blob is not found.
    """
    # Strategy A: __PWS_DATA__ JSON blob
    for var_name in ("__PWS_DATA__", "__INITIAL_STATE__", "__PWS_PROPS__"):
        pattern = rf"window\.{var_name}\s*=\s*(\{{.*?\}})(?:\s*;|\s*</script>)"
        m = re.search(pattern, page_html, re.DOTALL)
        if m:
            try:
                data = json.loads(m.group(1))
                # Walk the JSON tree looking for 'orig' image dict with 'url' key
                found = _find_pinterest_orig(data, depth=0)
                if found:
                    upgraded = _upgrade_pinterest_url(found)
                    print(f"[STAGE] verify:   -> Pinterest PWS_DATA orig image: {upgraded[:80]}")
                    return upgraded
            except (json.JSONDecodeError, RecursionError):
                pass

    # Strategy B: JSON-LD
    json_ld = re.search(
        r'<script[^>]+type=["\']application/ld\+json["\'][^>]*>(.*?)</script>',
        page_html, re.DOTALL | re.IGNORECASE
    )
    if json_ld:
        try:
            data = json.loads(json_ld.group(1))
            for key in ("image", "thumbnailUrl", "contentUrl"):
                val = data.get(key)
                if isinstance(val, str) and val.startswith("http"):
                    upgraded = _upgrade_pinterest_url(val)
                    print(f"[STAGE] verify:   -> Pinterest JSON-LD image: {upgraded[:80]}")
                    return upgraded
                if isinstance(val, dict):
                    for subkey in ("url", "contentUrl"):
                        sub = val.get(subkey, "")
                        if sub.startswith("http"):
                            upgraded = _upgrade_pinterest_url(sub)
                            print(f"[STAGE] verify:   -> Pinterest JSON-LD image: {upgraded[:80]}")
                            return upgraded
        except (json.JSONDecodeError, AttributeError):
            pass

    return None


def _find_pinterest_orig(obj: object, depth: int) -> str | None:
    """
    Recursively walks a parsed JSON object to find a Pinterest 'orig'
    image dict of the form {"url": "https://i.pinimg.com/originals/..."}
    Stops at depth 20 to avoid stack overflow on very large blobs.
    """
    if depth > 20:
        return None
    if isinstance(obj, dict):
        # Pinterest stores images as {"orig": {"url": "...", "width": ..., "height": ...}}
        orig = obj.get("orig")
        if isinstance(orig, dict):
            url = orig.get("url", "")
            if url.startswith("http") and "pinimg.com" in url:
                return url
        for val in obj.values():
            result = _find_pinterest_orig(val, depth + 1)
            if result:
                return result
    elif isinstance(obj, list):
        for item in obj:
            result = _find_pinterest_orig(item, depth + 1)
            if result:
                return result
    return None


# ---------------------------------------------------------------------------
# Platform-specific: LinkedIn
# ---------------------------------------------------------------------------

def _extract_linkedin_best_image(page_html: str) -> str | None:
    """
    LinkedIn's og:image is a tiny (~200px) resampled CDN thumbnail.
    The full-resolution profile photo URL (media.licdn.com/dms/image/...) is
    always present in the page HTML — either in a data-delayed-url attribute,
    a data-ghost-url attribute, a <img> src, or inside a <script> JSON blob.

    Tries in order:
      1. data-delayed-url on <img> tags (LinkedIn lazy-loading)
      2. data-ghost-url  (LinkedIn skeleton loaders)
      3. Any media.licdn.com URL present in the HTML (most reliable fallback)
    """

    # Pattern 1: data-delayed-url containing the real profile photo CDN URL
    m = re.search(
        r'data-delayed-url=["\']([^"\']*media\.licdn\.com/dms/image[^"\']+)["\']',
        page_html, re.IGNORECASE
    )
    if m:
        url = m.group(1).strip()
        print(f"[STAGE] verify:   -> LinkedIn data-delayed-url: {url[:80]}")
        return url

    # Pattern 2: data-ghost-url
    m = re.search(
        r'data-ghost-url=["\']([^"\']*media\.licdn\.com/dms/image[^"\']+)["\']',
        page_html, re.IGNORECASE
    )
    if m:
        url = m.group(1).strip()
        print(f"[STAGE] verify:   -> LinkedIn data-ghost-url: {url[:80]}")
        return url

    # Pattern 3: Any media.licdn.com/dms/image URL (inside JSON blobs, script tags etc.)
    # Exclude profile-displayphoto-shrink to get the largest variant
    all_cdn = re.findall(
        r'(https?://media\.licdn\.com/dms/image/[^\s\'"<>]+)',
        page_html, re.IGNORECASE
    )
    # Prefer URLs that are NOT the tiny shrink variants
    non_shrink = [u for u in all_cdn if "shrink_100" not in u and "shrink_50" not in u]
    preferred = non_shrink if non_shrink else all_cdn
    if preferred:
        # Pick the longest URL — it's usually the highest quality (more path params)
        best = max(preferred, key=len)
        print(f"[STAGE] verify:   -> LinkedIn CDN URL (raw scan): {best[:80]}")
        return best

    return None


# ---------------------------------------------------------------------------
# Generic image extraction
# ---------------------------------------------------------------------------

def _extract_best_image_url(page_html: str, page_url: str) -> str | None:
    """
    Extracts the highest-quality face image URL from a page.

    Priority order:
      1. LinkedIn-specific extractor (full-res CDN URL)
      2. Pinterest-specific extractor (originals CDN URL)
      3. og:image / twitter:image meta tags  (upgraded for Pinterest)
      4. Largest <img> src on the page
    """
    page_url_lower = page_url.lower()

    # --- Priority 1: LinkedIn ---
    if "linkedin.com" in page_url_lower:
        url = _extract_linkedin_best_image(page_html)
        if url:
            return url
        print("[STAGE] verify:   -> LinkedIn extractor found nothing; falling back to og:image.")

    # --- Priority 2: Pinterest ---
    if "pinterest" in page_url_lower:
        url = _extract_pinterest_best_image(page_html)
        if url:
            return url
        print("[STAGE] verify:   -> Pinterest extractor found nothing; falling back to og:image.")

    # --- Priority 3: og:image / twitter:image meta tags ---
    meta_patterns = [
        r'<meta[^>]+property=["\']og:image["\'][^>]+content=["\']([^"\']+)["\']',
        r'<meta[^>]+content=["\']([^"\']+)["\'][^>]+property=["\']og:image["\']',
        r'<meta[^>]+name=["\']twitter:image(?::src)?["\'][^>]+content=["\']([^"\']+)["\']',
        r'<meta[^>]+content=["\']([^"\']+)["\'][^>]+name=["\']twitter:image(?::src)?["\']',
    ]
    for pattern in meta_patterns:
        m = re.search(pattern, page_html, re.IGNORECASE)
        if m:
            raw = m.group(1).strip()
            if raw and not raw.endswith('.svg'):
                # Upgrade Pinterest CDN URLs found in meta tags
                url = _upgrade_pinterest_url(raw)
                print(f"[STAGE] verify:   -> Meta image extracted: {url[:80]}")
                return url

    # --- Priority 4: Largest <img> tag ---
    img_tags = re.findall(
        r'<img[^>]+src=["\']([^"\']+)["\'][^>]*(?:width=["\'](\d+)["\'])?',
        page_html, re.IGNORECASE
    )
    candidates = [
        (src, int(w) if w else 0)
        for src, w in img_tags
        if src.startswith("http") and not src.endswith('.svg')
    ]
    if candidates:
        candidates.sort(key=lambda x: x[1], reverse=True)
        best_src = _upgrade_pinterest_url(candidates[0][0])
        print(f"[STAGE] verify:   -> Fallback img src: {best_src[:80]}")
        return best_src

    print("[STAGE] verify:   -> No image URL found in page.")
    return None


# ---------------------------------------------------------------------------
# Download helpers
# ---------------------------------------------------------------------------

def _download_url(url: str, timeout: int = 30) -> str | None:
    """Downloads a URL to a temp file. Returns path or None on failure."""
    try:
        resp = requests.get(url, timeout=timeout, stream=True, headers=_HEADERS)
        resp.raise_for_status()
        # Detect content type for correct suffix
        ct = resp.headers.get("Content-Type", "")
        suffix = ".webp" if "webp" in ct else ".jpg"
        with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
            for chunk in resp.iter_content(chunk_size=8192):
                tmp.write(chunk)
            return tmp.name
    except Exception as e:
        print(f"[STAGE] verify:   -> Download failed ({type(e).__name__}): {e}")
        return None


def _download_image(url: str) -> str | None:
    """
    Downloads the best-quality image reachable from `url`.
    If it's a webpage, runs platform-specific + generic extraction first.
    """
    if _is_direct_image(url):
        # Still upgrade Pinterest CDN URLs that arrive as direct image URLs
        return _download_url(_upgrade_pinterest_url(url))

    # It's a webpage — fetch HTML and extract the best image URL
    try:
        page_resp = requests.get(url, timeout=15, headers=_HEADERS)
        page_resp.raise_for_status()
        best_url = _extract_best_image_url(page_resp.text, url)
    except Exception as e:
        print(f"[STAGE] verify:   -> Failed to fetch page ({type(e).__name__}): {e}")
        return None

    if best_url:
        return _download_url(best_url)

    print("[STAGE] verify:   -> Last resort: downloading page URL directly as image.")
    return _download_url(url)


# ---------------------------------------------------------------------------
# Image size validation
# ---------------------------------------------------------------------------

def _check_image_size(image_path: str) -> tuple[int, int]:
    """
    Returns (width, height) of image_path using PIL.
    Returns (0, 0) if the file cannot be opened.
    """
    try:
        from PIL import Image  # pyrefly: ignore [missing-import]
        with Image.open(image_path) as img:
            return img.size  # (width, height)
    except Exception:
        return (0, 0)


# ---------------------------------------------------------------------------
# Embedding extraction (all faces in candidate image)
# ---------------------------------------------------------------------------

def _get_all_embeddings(image_path: str) -> list[list[float]]:
    """
    Extract embeddings for ALL faces found in image_path.

    Improvements over the previous version:
    - align=True: DeepFace aligns each face to a canonical pose via landmark
      detection before embedding. This is critical for side-profile photos and
      slightly angled headshots (very common on LinkedIn/Pinterest).
    - Size gate: rejects images smaller than _MIN_FACE_PX on either dimension
      before attempting embedding, since tiny images produce garbage vectors.

    Returns a list of embeddings (may be empty if no face detected or image
    is too small).
    """
    from deepface import DeepFace  # pyrefly: ignore [missing-import]

    # --- Size gate ---
    w, h = _check_image_size(image_path)
    if w < _MIN_FACE_PX or h < _MIN_FACE_PX:
        print(
            f"[STAGE] verify:   -> Image too small ({w}×{h}px, min {_MIN_FACE_PX}px) "
            "— skipping embedding."
        )
        return []

    print(f"[STAGE] verify:   -> Image size OK ({w}×{h}px). Running face detection...")

    try:
        results = DeepFace.represent(
            img_path=image_path,
            model_name="Facenet512",
            detector_backend="mtcnn",
            align=True,          # ← landmark alignment for accurate embedding
            enforce_detection=True,
        )
        if not isinstance(results, list):
            results = [results]
        embeddings = [r["embedding"] for r in results if "embedding" in r]
        n = len(embeddings)
        if n == 0:
            print("[STAGE] verify:   -> No embeddings returned by DeepFace.")
        elif n == 1:
            print("[STAGE] verify:   -> 1 face detected and embedded.")
        else:
            print(f"[STAGE] verify:   -> {n} faces found in candidate — scoring all.")
        return embeddings
    except ValueError:
        print("[STAGE] verify:   -> No face detected (ValueError from DeepFace).")
        return []
    except Exception as e:
        print(f"[STAGE] verify:   -> Embedding extraction error: {type(e).__name__}: {e}")
        return []


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def verify_candidates(
    original_embedding: list[float],
    candidates: list[dict],
    threshold: float = 0.45,
    max_candidates: int = 10,
    max_workers: int = 4,
) -> list[dict]:
    """
    For each candidate (up to max_candidates):
      1. Downloads the best available image using platform-specific extraction.
      2. Validates image size (must be >= 80x80px).
      3. Detects ALL faces in that image with landmark alignment.
      4. Scores each face via cosine similarity; keeps the best score.

    Verification runs in parallel (max_workers threads) for speed.
    Returns only candidates scoring >= threshold, sorted descending by score.
    """
    if not candidates:
        print("[STAGE] verify: No candidates to verify.")
        return []

    # Honour max_candidates cap for speed
    if len(candidates) > max_candidates:
        print(f"[STAGE] verify: Capping at {max_candidates}/{len(candidates)} candidates for speed.")
        candidates = candidates[:max_candidates]

    print(f"[STAGE] verify: Verifying {len(candidates)} candidate(s) at threshold={threshold} (workers={max_workers})")

    def _verify_one(args: tuple[int, dict]) -> dict | None:
        """Verify a single candidate. Returns the enriched dict or None."""
        i, candidate = args
        page_url  = candidate.get("page_url", "")
        image_url = candidate.get("image_url", "")
        print(f"[STAGE] verify: [{i + 1}/{len(candidates)}] {page_url[:80]}")

        if not image_url and not page_url:
            return None

        # Try direct image_url first, then scrape the page
        tmp_path: str | None = None
        if image_url:
            tmp_path = _download_image(image_url)
        if tmp_path is None and page_url:
            tmp_path = _download_image(page_url)
        if tmp_path is None:
            print(f"[STAGE] verify:   -> Could not obtain image — skipping.")
            return None

        all_embeddings = _get_all_embeddings(tmp_path)
        try:
            os.remove(tmp_path)
        except OSError:
            pass

        if not all_embeddings:
            print(f"[STAGE] verify:   -> No usable face — skipping.")
            return None

        valid = [emb for emb in all_embeddings if len(emb) == len(original_embedding)]
        if not valid:
            return None

        best_score = max(_cosine_similarity(original_embedding, emb) for emb in valid)
        verdict = "ACCEPTED" if best_score >= threshold else "REJECTED"
        print(f"[STAGE] verify:   -> Best score: {best_score:.4f} [{verdict}]")

        if best_score >= threshold:
            return {**candidate, "similarity_score": round(best_score, 4)}
        return None

    # Run verifications in parallel
    accepted: list[dict] = []
    indexed = list(enumerate(candidates))

    with ThreadPoolExecutor(max_workers=max_workers) as pool:
        futures = {pool.submit(_verify_one, item): item for item in indexed}
        for future in as_completed(futures):
            try:
                result = future.result()
                if result is not None:
                    accepted.append(result)
            except Exception as exc:
                print(f"[STAGE] verify: Worker error: {exc}")

    accepted.sort(key=lambda x: x["similarity_score"], reverse=True)
    print(f"[STAGE] verify: {len(accepted)} candidate(s) accepted above threshold {threshold}.")
    return accepted


if __name__ == "__main__":
    # Standalone test: self-similarity should always be 1.0
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
