import os
import requests
from dotenv import load_dotenv

load_dotenv()

PINATA_JWT = os.getenv("PINATA_JWT", "")
PINATA_PIN_URL = "https://api.pinata.cloud/pinning/pinFileToIPFS"
PINATA_GATEWAY = "https://gateway.pinata.cloud/ipfs"


def pin_file(file_path: str) -> dict:
    """
    Pins a local file to IPFS via Pinata and returns a public gateway URL.
    Returns {"cid": str, "gateway_url": str} on success.
    Returns {"error": str} if PINATA_JWT is missing or the call fails.
    STOP behaviour: if credentials are absent, prints a clear message and
    returns an error dict — does NOT invent a URL.
    """
    if not PINATA_JWT:
        print("[STAGE] ipfs_utils: PINATA_JWT not set — cannot pin file.")
        print("[STAGE] ipfs_utils: STOP — supply PINATA_JWT in .env before continuing.")
        return {"error": "PINATA_JWT_missing"}

    print(f"[STAGE] ipfs_utils: Pinning {file_path} to IPFS via Pinata ...")
    try:
        with open(file_path, "rb") as fh:
            response = requests.post(
                PINATA_PIN_URL,
                headers={"Authorization": f"Bearer {PINATA_JWT}"},
                files={"file": fh},
                timeout=60,
            )
        response.raise_for_status()
        data = response.json()
        cid = data["IpfsHash"]
        gateway_url = f"{PINATA_GATEWAY}/{cid}?filename=image.jpg"
        print(f"[STAGE] ipfs_utils: Pinned. CID={cid}")
        return {"cid": cid, "gateway_url": gateway_url}
    except requests.RequestException as e:
        print(f"[STAGE] ipfs_utils: HTTP error — {type(e).__name__}: {e}")
        return {"error": str(e)}
    except KeyError:
        print(f"[STAGE] ipfs_utils: Unexpected Pinata response shape: {response.text}")
        return {"error": "unexpected_pinata_response"}


def pin_json(data: dict, name: str = "evidence.json") -> dict:
    """
    Pins a JSON payload to IPFS via Pinata.
    Returns {"cid": str, "gateway_url": str} on success.
    """
    if not PINATA_JWT:
        print("[STAGE] ipfs_utils: PINATA_JWT not set — cannot pin JSON.")
        return {"error": "PINATA_JWT_missing"}

    print(f"[STAGE] ipfs_utils: Pinning JSON '{name}' to IPFS ...")
    try:
        response = requests.post(
            "https://api.pinata.cloud/pinning/pinJSONToIPFS",
            headers={
                "Authorization": f"Bearer {PINATA_JWT}",
                "Content-Type": "application/json",
            },
            json={"pinataContent": data, "pinataMetadata": {"name": name}},
            timeout=30,
        )
        response.raise_for_status()
        cid = response.json()["IpfsHash"]
        gateway_url = f"{PINATA_GATEWAY}/{cid}"
        print(f"[STAGE] ipfs_utils: JSON pinned. CID={cid}")
        return {"cid": cid, "gateway_url": gateway_url}
    except requests.RequestException as e:
        print(f"[STAGE] ipfs_utils: HTTP error — {type(e).__name__}: {e}")
        return {"error": str(e)}
    except KeyError:
        print(f"[STAGE] ipfs_utils: Unexpected Pinata response shape: {response.text}")
        return {"error": "unexpected_pinata_response"}


if __name__ == "__main__":
    import sys
    if len(sys.argv) > 1:
        result = pin_file(sys.argv[1])
        print(f"[STAGE] ipfs_utils: Result -> {result}")
    else:
        print("[STAGE] ipfs_utils: Pass a file path to test pin_file.")
