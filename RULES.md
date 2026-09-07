---
trigger: always_on
description: Layer boundaries, pinned stack, and security for faceid-chain-verify
---
LAYER: CV → src/capture.py, src/face_id.py only
LAYER: UTIL → src/ipfs_utils.py only
LAYER: SEARCH → src/search.py, src/verify_match.py only
LAYER: CHAIN → src/chain.py, abi/, chain env vars only
LAYER: Both → only files explicitly listed in the prompt
Never write/redeploy the contract — hand-deployed via Remix.

Python 3.11 only, no Node/npm. deepface (Facenet512/opencv), never insightface directly.
Apify actor johnvc/yandex-reverse-image-search, never PimEyes. web3.py, never ethers.js.
Before adding any new package not in requirements.txt: STOP and ask.

All keys (APIFY_TOKEN, SEPOLIA_RPC_URL, WALLET_PRIVATE_KEY, CONTRACT_ADDRESS, PINATA_JWT) in .env only.
.env in .gitignore before first commit. Never log a raw embedding or a private key.
