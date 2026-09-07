import os
import sys
import requests
from dotenv import load_dotenv

# Import UTIL layer — do not duplicate its logic
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from ipfs_utils import pin_file

load_dotenv()

APIFY_TOKEN = os.getenv("APIFY_TOKEN") or os.getenv("APIFY_API_TOKEN", "")
APIFY_ACTOR_URL = (
    "https://api.apify.com/v2/acts/johnvc~yandex-reverse-image-search"
    "/run-sync-get-dataset-items"
)
ALLOWED_DOMAINS = {
    "instagram.com",
    "x.com",
    "twitter.com",
    "linkedin.com",
    "facebook.com",
    "pinterest.com",
}


def _domain_allowed(url: str) -> bool:
    """Returns True if the URL's hostname matches an allowed social domain."""
    try:
        from urllib.parse import urlparse
        host = urlparse(url).netloc.lower()
        # strip www. prefix
        host = host.removeprefix("www.")
        return any(host == d or host.endswith(f".{d}") for d in ALLOWED_DOMAINS)
    except Exception:
        return False


def find_candidates(image_path: str) -> list[dict]:
    """
    Pins image_path to IPFS to obtain a public URL, then queries the
    Apify johnvc/yandex-reverse-image-search actor.
    Returns a filtered list of social-media candidate dicts:
        [{"page_url": ..., "image_url": ..., "source": ...}, ...]
    Returns [] on any failure — never fabricates results.
    """
    print(f"[STAGE] search: Starting candidate search for {image_path}")

    # --- Step 1: get a public URL via IPFS ---
    if not APIFY_TOKEN:
        print("[STAGE] search: APIFY_TOKEN not set — cannot call Yandex search.")
        print("[STAGE] search: STOP — supply APIFY_TOKEN in .env before continuing.")
        return []

    pin_result = pin_file(image_path)
    if "error" in pin_result:
        print(f"[STAGE] search: pin_file failed with {pin_result} — cannot continue.")
        print("[STAGE] search: STOP — a public image URL is required for Apify.")
        return []

    gateway_url = pin_result["gateway_url"]
    print(f"[STAGE] search: Image pinned. Public URL: {gateway_url}")

    # --- Step 1.5: Upload to a bot-friendly host for Apify (IPFS gateways block scrapers) ---
    print("[STAGE] search: Uploading to temporary host (catbox.moe) for Yandex scraper...")
    try:
        with open(image_path, "rb") as fh:
            c_resp = requests.post(
                "https://catbox.moe/user/api.php",
                data={"reqtype": "fileupload"},
                files={"fileToUpload": fh},
                timeout=30
            )
        c_resp.raise_for_status()
        temp_url = c_resp.text.strip()
        print(f"[STAGE] search: Temporary URL generated: {temp_url}")
    except Exception as e:
        print(f"[STAGE] search: Temporary upload failed — {e}")
        return []

    # --- Step 2: call Apify actor ---
    print("[STAGE] search: Calling Apify Yandex reverse-image-search actor ...")
    try:
        response = requests.post(
            APIFY_ACTOR_URL,
            params={"token": APIFY_TOKEN},
            json={"image_url": temp_url, "include_matching_pages": True},
            timeout=120,
        )
        response.raise_for_status()
    except requests.RequestException as e:
        print(f"[STAGE] search: Apify HTTP error — {type(e).__name__}: {e}")
        return []

    try:
        raw_items = response.json()
    except ValueError as e:
        print(f"[STAGE] search: Failed to parse Apify response as JSON — {e}")
        print(f"[STAGE] search: Raw response text: {response.text[:2000]}")
        return []

    if not isinstance(raw_items, list):
        print("[STAGE] search: Unexpected Apify response shape — expected a list.")
        print(f"[STAGE] search: Raw response: {raw_items}")
        return []

    print(f"[STAGE] search: Apify returned {len(raw_items)} raw item(s).")

    # --- Step 3: extract, filter by domain, and deduplicate ---
    from urllib.parse import urlparse

    candidates: list[dict] = []
    seen_keys: set[str] = set()

    for item in raw_items:
        if not isinstance(item, dict):
            print(f"[STAGE] search: Unexpected item type {type(item)} — skipping.")
            continue

        # Validate expected fields exist — stop if shape is wrong
        page_url = item.get("pageUrl") or item.get("page_url") or item.get("link", "")
        if not page_url:
            print("[STAGE] search: STOP — response item missing 'pageUrl'/'page_url'/'link'.")
            print(f"[STAGE] search: Actual item keys: {list(item.keys())}")
            print(f"[STAGE] search: Full item: {item}")
            return []

        # Prefer the full-res 'original' image from Yandex over the thumbnail
        image_url = (
            item.get("original") or
            item.get("imageUrl") or
            item.get("image_url") or
            item.get("thumbnail") or
            ""
        )
        source = item.get("source", "")

        # Check the page URL against allowed domains
        if not _domain_allowed(page_url):
            continue

        # Deduplicate: use the URL path as a key so the same pin on
        # ch.pinterest.com / ie.pinterest.com / ru.pinterest.com all collapse to one
        dedup_key = urlparse(page_url).path.rstrip("/")
        if dedup_key in seen_keys:
            continue
        seen_keys.add(dedup_key)

        candidates.append({
            "page_url": page_url,
            "image_url": image_url,
            "source": source,
        })

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
