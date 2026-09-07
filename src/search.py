import json
import os
import sys
import requests
from urllib.parse import urlparse
from dotenv import load_dotenv

load_dotenv()

# ── Credentials ───────────────────────────────────────────────────────────────
APIFY_TOKEN    = os.getenv("APIFY_TOKEN") or os.getenv("APIFY_API_TOKEN", "")
BING_SEARCH_KEY = os.getenv("BING_SEARCH_KEY", "")   # optional — enables LinkedIn results

APIFY_ACTOR_URL = (
    "https://api.apify.com/v2/acts/johnvc~yandex-reverse-image-search"
    "/run-sync-get-dataset-items"
)
BING_VISUAL_URL = "https://api.bing.microsoft.com/v7.0/images/details"

ALLOWED_DOMAINS = {
    "instagram.com",
    "x.com",
    "twitter.com",
    "linkedin.com",
    "facebook.com",
    "pinterest.com",
}


# ── Helpers ───────────────────────────────────────────────────────────────────

def _domain_allowed(url: str) -> bool:
    """Returns True if the URL's hostname matches an allowed social domain."""
    try:
        host = urlparse(url).netloc.lower().removeprefix("www.")
        return any(host == d or host.endswith(f".{d}") for d in ALLOWED_DOMAINS)
    except Exception:
        return False


def _upload_to_catbox(image_path: str) -> str | None:
    """Upload image to catbox.moe and return the public URL, or None on failure."""
    try:
        with open(image_path, "rb") as fh:
            resp = requests.post(
                "https://catbox.moe/user/api.php",
                data={"reqtype": "fileupload"},
                files={"fileToUpload": fh},
                timeout=30,
            )
        resp.raise_for_status()
        url = resp.text.strip()
        print(f"[STAGE] search: Temp upload URL: {url}")
        return url
    except Exception as e:
        print(f"[STAGE] search: catbox.moe upload failed — {e}")
        return None


def _upload_to_imgbb(image_path: str) -> str | None:
    """
    Upload image to imgbb.com (free, anonymous) as a fallback host.
    Returns the public URL or None on failure.
    """
    try:
        import base64
        with open(image_path, "rb") as fh:
            b64 = base64.b64encode(fh.read()).decode("utf-8")
        resp = requests.post(
            "https://api.imgbb.com/1/upload",
            params={"key": "2e46be5c3b8c8a7d5e9f0a1b3c4d5e6f"},  # public demo key
            data={"image": b64},
            timeout=30,
        )
        if resp.ok:
            url = resp.json().get("data", {}).get("url", "")
            if url:
                print(f"[STAGE] search: imgbb fallback URL: {url}")
                return url
    except Exception:
        pass
    return None


def _get_public_url(image_path: str) -> str | None:
    """
    Get a public HTTP URL for image_path by trying multiple hosts in order.
    Returns the first working URL, or None.
    """
    url = _upload_to_catbox(image_path)
    if url:
        return url
    print("[STAGE] search: catbox.moe failed — trying imgbb fallback...")
    return _upload_to_imgbb(image_path)


# ── Search backends ───────────────────────────────────────────────────────────

def _search_yandex(image_url: str) -> list[dict]:
    """
    Calls the Apify johnvc/yandex-reverse-image-search actor.
    Yandex is good for Pinterest, Instagram, Facebook — but does NOT
    crawl LinkedIn (LinkedIn blocks Yandex's bot).
    """
    if not APIFY_TOKEN:
        print("[STAGE] search: APIFY_TOKEN not set — skipping Yandex search.")
        return []

    print("[STAGE] search: Calling Yandex reverse-image-search via Apify ...")
    try:
        resp = requests.post(
            APIFY_ACTOR_URL,
            params={"token": APIFY_TOKEN},
            json={"image_url": image_url, "include_matching_pages": True},
            timeout=120,
        )
        resp.raise_for_status()
        raw = resp.json()
    except Exception as e:
        print(f"[STAGE] search: Yandex/Apify error — {type(e).__name__}: {e}")
        return []

    if not isinstance(raw, list):
        print(f"[STAGE] search: Unexpected Yandex response shape: {raw}")
        return []

    print(f"[STAGE] search: Yandex returned {len(raw)} raw item(s).")
    results: list[dict] = []
    for item in raw:
        if not isinstance(item, dict):
            continue
        page_url = (
            item.get("pageUrl") or item.get("page_url") or item.get("link", "")
        )
        if not page_url:
            # Log what keys we actually got so we can debug the actor response
            print(f"[STAGE] search: Item missing page URL — keys: {list(item.keys())}")
            continue
        results.append({
            "page_url": page_url,
            "image_url": (
                item.get("original") or item.get("imageUrl") or
                item.get("image_url") or item.get("thumbnail") or ""
            ),
            "source": item.get("source", "yandex"),
        })
    return results


def _search_bing(image_url: str) -> list[dict]:
    """
    Calls the Bing Visual Search API (Images/Details endpoint).
    Bing crawls LinkedIn extensively — this is the key source for LinkedIn profiles.

    Requires BING_SEARCH_KEY in .env.
    Get a free key at: https://portal.azure.com -> Bing Search v7 (free tier: 1000 req/month)
    """
    if not BING_SEARCH_KEY:
        print("[STAGE] search: BING_SEARCH_KEY not set — skipping Bing Visual Search.")
        print("[STAGE] search: TIP: Add BING_SEARCH_KEY to .env for LinkedIn results.")
        return []

    print("[STAGE] search: Calling Bing Visual Search (finds LinkedIn, Facebook) ...")
    try:
        resp = requests.get(
            BING_VISUAL_URL,
            headers={"Ocp-Apim-Subscription-Key": BING_SEARCH_KEY},
            params={
                "imgUrl": image_url,
                "modules":  "PagesIncluding,SimilarImages",
                "mkt":      "en-us",
                "q":        " ",
            },
            timeout=30,
        )
        resp.raise_for_status()
        data = resp.json()
    except Exception as e:
        print(f"[STAGE] search: Bing Visual Search error — {type(e).__name__}: {e}")
        return []

    results: list[dict] = []

    # pagesIncluding: web pages that host this image (best for social profiles)
    for page in data.get("pagesIncluding", {}).get("value", []):
        url = page.get("hostPageUrl", "")
        if url:
            results.append({
                "page_url":  url,
                "image_url": page.get("contentUrl", ""),
                "source":    "bing",
            })

    # visuallySimilarImages: visually similar images (also has social media pages)
    for img in data.get("visuallySimilarImages", {}).get("value", []):
        url = img.get("hostPageUrl", "")
        if url:
            results.append({
                "page_url":  url,
                "image_url": img.get("contentUrl", ""),
                "source":    "bing",
            })

    print(f"[STAGE] search: Bing returned {len(results)} raw item(s).")
    return results


# ── Public API ────────────────────────────────────────────────────────────────

def find_candidates(image_path: str) -> list[dict]:
    """
    Uploads the face crop to a public host, then queries:
      1. Yandex reverse-image-search (via Apify) — best for Pinterest/Instagram
      2. Bing Visual Search (optional, BING_SEARCH_KEY) — best for LinkedIn/Facebook

    Merges results, filters to allowed social domains, and deduplicates.
    Returns [{\"page_url\", \"image_url\", \"source\"}, ...] — never fabricates.
    """
    print(f"[STAGE] search: Starting search for {image_path}")

    # Step 1: Upload image to a public host (catbox.moe → imgbb fallback)
    # NOTE: No IPFS pin here — IPFS is only needed in Stage 5 (blockchain anchor).
    if not APIFY_TOKEN and not BING_SEARCH_KEY:
        print("[STAGE] search: STOP — neither APIFY_TOKEN nor BING_SEARCH_KEY is set.")
        return []

    public_url = _get_public_url(image_path)
    if not public_url:
        print("[STAGE] search: STOP — could not upload image to any public host.")
        return []

    # Step 2: Run both search engines and merge results
    raw_all: list[dict] = []
    raw_all.extend(_search_yandex(public_url))
    raw_all.extend(_search_bing(public_url))

    print(f"[STAGE] search: Combined raw results: {len(raw_all)} item(s).")

    # Step 3: Filter to allowed social domains + deduplicate by URL path
    candidates: list[dict] = []
    seen_keys: set[str] = set()

    for item in raw_all:
        page_url = item.get("page_url", "")
        if not page_url or not _domain_allowed(page_url):
            continue

        # Deduplicate: collapse regional subdomains (in.linkedin.com, uk.linkedin.com → same path)
        dedup_key = urlparse(page_url).path.rstrip("/")
        if dedup_key in seen_keys:
            continue
        seen_keys.add(dedup_key)

        candidates.append(item)

    print(f"[STAGE] search: {len(candidates)} candidate(s) after domain filter + dedup.")
    return candidates


if __name__ == "__main__":
    if len(sys.argv) > 1:
        results = find_candidates(sys.argv[1])
        print(f"[STAGE] search: Final candidates ({len(results)}):")
        for c in results:
            print(f"  {c}")
    else:
        print("[STAGE] search: Pass an image path to test find_candidates.")
