# FaceID-Chain Verify 🔗

> **HH Goa 2026 Hackathon — Task 3: Face Identification & Blockchain Verification**

A fully automated CLI pipeline that takes a face image as input, reverse-searches the web for matching social media profiles, mathematically verifies each match using deep-learning face embeddings, and anchors tamper-evident evidence permanently on the Ethereum blockchain.

---

## Pipeline Architecture

```
[Input Image / Webcam / Clipboard]
         │
         ▼
[Stage 1] Capture          — webcam, local file, or clipboard paste (Win+Shift+S)
         │
         ▼
[Stage 2] Face Embedding   — DeepFace + Facenet512 + MTCNN, 512-d vector
         │
         ▼
[Stage 2.5] Face Crop      — Tight head crop sent to Yandex (removes page noise)
         │
         ▼
[Stage 3] Reverse Search   — Apify · Yandex Reverse Image Search actor
          Filtered to: LinkedIn, Instagram, X/Twitter, Facebook, Pinterest
         │
         ▼
[Stage 4] Verify Matches   — Download candidate profile photo
          ├─ LinkedIn: full-res media.licdn.com CDN URL extracted from page HTML
          ├─ Pinterest: originals/ resolution extracted from __PWS_DATA__ JSON blob
          └─ Cosine similarity vs. query embedding (aligned Facenet512 vectors)
         │
         ▼
[Stage 5] Blockchain Anchor — Pin evidence JSON to IPFS (Pinata)
          keccak256 hash submitted to FaceVerificationRegistry on Ethereum Sepolia
         │
         ▼
[Stage 6] Tamper Demo      — On-chain re-verification proves immutability;
          tampered hash returns exists=False
```

---

## Tech Stack

| Component | Technology |
|---|---|
| Face detection | DeepFace + MTCNN detector |
| Face embedding | Facenet512 (512-d, landmark-aligned) |
| Reverse image search | Apify · `johnvc/yandex-reverse-image-search` actor |
| Decentralised storage | IPFS via Pinata API |
| Blockchain | Ethereum Sepolia Testnet |
| Smart contract | Solidity `FaceVerificationRegistry`, deployed via Remix |
| Blockchain client | web3.py |

---

## Blockchain Details

- **Network:** Ethereum Sepolia Testnet (public, free test ETH)
- **Contract:** `FaceVerificationRegistry.sol` — stores `keccak256(evidence_JSON)` + IPFS CID on-chain
- **Deployed Address:** `0x325065332cc48D2fC230Ba1BF29dfF01fDc0c209`
- **Etherscan Explorer:** https://sepolia.etherscan.io/address/0x325065332cc48D2fC230Ba1BF29dfF01fDc0c209
- **Tamper detection:** Any modification to the evidence JSON changes its hash — `verifyRecord()` returns `exists=False`, cryptographically proving tampering.

---

## How to Run

### Prerequisites
- Python 3.11
- API keys for: **Apify** and **Pinata**
- A wallet funded with Sepolia test ETH (free from https://sepoliafaucet.com)

### 1. Clone & install
```powershell
git clone https://github.com/shreyansh-prasad/FVBChain.git
cd FVBChain
python -m venv venv
.\venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

### 2. Configure secrets
Copy `.env.example` to `.env` and fill in all values:
```powershell
Copy-Item .env.example .env
```

```env
APIFY_TOKEN=your_apify_api_token
PINATA_JWT=your_pinata_jwt_token
SEPOLIA_RPC_URL=https://ethereum-sepolia-rpc.publicnode.com
WALLET_PRIVATE_KEY=your_wallet_private_key_without_0x
CONTRACT_ADDRESS=0x325065332cc48D2fC230Ba1BF29dfF01fDc0c209
```

> ⚠️ Never commit `.env` to Git. It is already in `.gitignore`.

### 3. Run the pipeline

**Option A — Webcam capture** (press SPACE to snap):
```powershell
.\venv\Scripts\python.exe src\pipeline.py
```

**Option B — Local image file:**
```powershell
.\venv\Scripts\python.exe src\pipeline.py --image path\to\photo.jpg
```

**Option C — Clipboard screenshot** (after Win+Shift+S → copy to clipboard):
```powershell
.\venv\Scripts\python.exe src\pipeline.py --clipboard
```

**Adjust similarity threshold** (default 0.45, higher = stricter):
```powershell
.\venv\Scripts\python.exe src\pipeline.py --image photo.jpg --threshold 0.60
```

### 4. Expected output
```
======================================================================
[PIPELINE] Starting FaceID-Chain Verification Pipeline
======================================================================
[STAGE 1] Capture Frame
[STAGE 2] Face Extraction & Embedding
[STAGE 2.5] Face crop saved (used for Yandex search)
[STAGE 3] Reverse Image Search (Social Media)
  -> X candidate(s) found on LinkedIn/Pinterest/Instagram
[STAGE 4] Candidate Verification
  -> Best score: 0.7821 [ACCEPTED]
[STAGE 5] Submit Evidence On-Chain (Sepolia)
  -> Tx Hash: 0xabc...
  -> Explorer: https://sepolia.etherscan.io/tx/0xabc...
  -> IPFS CID: Qm...
[STAGE 6] On-Chain Verification & Tamper Demo
  -> On-chain record exists: True
  -> Tamper detected — exists=False as expected ✓
======================================================================
[PIPELINE] SUCCESS - All stages completed.
======================================================================
```

---

## Project Structure

```
FVBChain/
├── src/
│   ├── pipeline.py        # Orchestrator — all 6 stages
│   ├── capture.py         # Stage 1: webcam / clipboard capture
│   ├── face_id.py         # Stage 2: DeepFace embedding + face crop
│   ├── search.py          # Stage 3: Apify/Yandex reverse search
│   ├── verify_match.py    # Stage 4: platform-specific image extraction + cosine similarity
│   ├── chain.py           # Stage 5/6: blockchain submit + verify
│   └── ipfs_utils.py      # Pinata IPFS pin helper
├── abi/
│   └── FaceVerificationRegistry.json   # Smart contract ABI
├── requirements.txt
├── .env.example
└── README.md
```

---

## Known Limitations

- **LinkedIn authentication wall:** LinkedIn frequently returns a login-gate instead of real profile HTML for unauthenticated requests. The system extracts the full-res profile photo when HTML is accessible, but cannot bypass LinkedIn's auth wall for fully gated profiles.
- **Apify free tier:** The Apify free credit ($5) is consumed per run. High-volume use requires a paid plan.
- **Yandex index coverage:** Only finds matches for faces that Yandex has crawled and indexed. Low-footprint individuals may not appear.
- **Similarity threshold:** The default threshold (0.45 cosine similarity) is tuned experimentally on a small dataset — not statistically calibrated across demographics.
- **Sepolia testnet only:** The blockchain component uses test ETH (not real funds). Porting to mainnet would require real ETH for gas.
- **Demo use only:** Not GDPR/DPDP compliant. Run only on consenting subjects (your own face, or with explicit permission).

---

## ⚠️ Responsible Use Notice

This tool is built for personal demonstration and consent-driven identity verification in a hackathon context. **Do not run this pipeline on third parties without their explicit consent.** The developers accept no liability for misuse.
