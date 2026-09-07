# Build Progress — faceid-chain-verify
## Stage 0 — Environment: [x] Done — Notes: Python 3.11 venv with opencv, deepface, web3, requests, python-dotenv
## Stage 1 — Capture + embedding: [x] Done — Notes: src/capture.py (OpenCV webcam) & src/face_id.py (Facenet512)
## Stage 2 — IPFS utils: [x] Done — Notes: src/ipfs_utils.py (Pinata API integration)
## Stage 3 — Search + verify: [x] Done — Notes: src/search.py (Apify Yandex actor) & src/verify_match.py (Cosine similarity)
## Stage 4 — Contract deployed: [x] Done — Address: 0x325065332cc48D2fC230Ba1BF29dfF01fDc0c209 — Etherscan: https://sepolia.etherscan.io/address/0x325065332cc48D2fC230Ba1BF29dfF01fDc0c209
## Stage 5 — Chain glue: [x] Done — Notes: src/chain.py (submitRecord, verifyRecord, demo_tamper via web3.py)
## Stage 6 — Pipeline integration: [x] Done — Notes: src/pipeline.py (single CLI entry point for all 6 stages)
## Stage 7 — README + recording: [x] Done

## Known Limitations (paste into README, add specifics as you hit them)
- Similarity threshold tuned by eye on one subject, not statistically calibrated
- Coverage limited to what Yandex has indexed; no guarantee for low-footprint people
- Apify/Yandex terms may restrict production use beyond this demo
- Not GDPR/DPDP compliant — demo-only