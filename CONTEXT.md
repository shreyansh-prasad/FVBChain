# Project Context
> Auto-maintained by /sync. Do not edit manually.

## Project Identity
- Name: faceid-chain-verify
- Stack: Python 3.11 only. No Node/npm anywhere in this repo.
- Type: CLI pipeline, no frontend, no server
- Package manager: pip (requirements.txt)

## Architecture
- Entry point: src/pipeline.py
- CV layer: src/capture.py, src/face_id.py
- UTIL layer: src/ipfs_utils.py
- SEARCH layer: src/search.py, src/verify_match.py
- CHAIN layer: src/chain.py, contract/FaceVerificationRegistry.sol, abi/FaceVerificationRegistry.json
- Tests: smoke_test.py (manual, no framework)

## Layer Map
### CV: src/capture.py, src/face_id.py
### UTIL: src/ipfs_utils.py
### SEARCH: src/search.py, src/verify_match.py
### CHAIN: src/chain.py, abi/, chain vars in .env
### GLUE (touches all, entry point only): src/pipeline.py

## Active Decisions
| Decision | Reason | Date |
|---|---|---|
| DeepFace + Facenet512, not raw InsightFace/buffalo_l | buffalo_l now requires emailing InsightFace for a license; Facenet512 has no such gate | 2026-09-06 |
| detector_backend="opencv" default | zero extra installs; upgrade to mtcnn only if time remains | 2026-09-06 |
| Yandex via Apify actor johnvc/yandex-reverse-image-search, not PimEyes | PimEyes excludes social media by design — fails the task requirement | 2026-09-06 |
| Contract hand-written, deployed via Remix + MetaMask, not Hardhat | zero local Node toolchain = zero dependency-install risk | 2026-09-06 |
| Sepolia testnet | verified active/recommended well past this deadline | 2026-09-06 |
| Query image + evidence JSON pinned to IPFS via Pinata; only hash+CID on-chain | Apify needs a public URL for the query image; standard minimal on-chain footprint | 2026-09-06 |

## Current Functionality (Stable — Do Not Break)
- [x] Webcam capture + embedding
- [x] IPFS pin helper (file + JSON)
- [x] Reverse-image search filtered to social domains
- [x] Re-embedding + similarity verification
- [x] Contract deployed to Sepolia
- [x] submit/verify/tamper-demo via web3.py
- [x] Full pipeline runs end-to-end from one command (`src/pipeline.py`)

## In Progress
Complete - All pipeline stages (1-6) implemented, integrated, and verified on-chain.

## Known Issues
- None.

## Installed Packages
opencv-python, deepface, tf-keras, requests, web3, python-dotenv, numpy

## Last Updated
2026-09-07 — All stages (1–6) complete & verified on Sepolia testnet.
