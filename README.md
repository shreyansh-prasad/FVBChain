# FaceID-Chain Verify

A CLI pipeline that captures a live face, reverse-searches it on social media, verifies similarity using Facenet512, and securely anchors the evidence on the Ethereum Sepolia blockchain.

## How to Run

**1. Environment Setup**
This pipeline requires Python 3.11. Create a virtual environment and install the required dependencies:
```powershell
python -m venv venv
.\venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

**2. Environment Variables (`.env`)**
Create a `.env` file in the project root containing:
- `APIFY_TOKEN`: Your Apify API token (for the johnvc/yandex-reverse-image-search actor).
- `PINATA_JWT`: Your Pinata JWT with `pinFileToIPFS` and `pinJSONToIPFS` scopes enabled.
- `SEPOLIA_RPC_URL`: Ethereum Sepolia RPC endpoint (e.g., `https://ethereum-sepolia-rpc.publicnode.com`).
- `WALLET_PRIVATE_KEY`: Private key of a wallet funded with Sepolia test ETH.
- `CONTRACT_ADDRESS`: The deployed FaceVerificationRegistry contract address (see below).

**3. Execution**
Run the full 6-stage automated pipeline with a single command (press **SPACE** when the webcam opens to snap the photo):
```powershell
.\venv\Scripts\python.exe src\pipeline.py
```
*(Optionally, bypass the webcam and provide a local image: `.\venv\Scripts\python.exe src\pipeline.py --image path/to/image.jpg`)*

## Smart Contract Details

- **Blockchain:** Ethereum Sepolia Testnet
- **Contract Address:** `0x325065332cc48D2fC230Ba1BF29dfF01fDc0c209`
- **Etherscan Explorer:** [https://sepolia.etherscan.io/address/0x325065332cc48D2fC230Ba1BF29dfF01fDc0c209](https://sepolia.etherscan.io/address/0x325065332cc48D2fC230Ba1BF29dfF01fDc0c209)

## ⚠️ Responsible Use

**Demo run only on consenting/own faces, not for identifying third parties without consent.** This tool is built for personal demonstration and consent-driven identity verification. Do not use this pipeline on others without their explicit permission.

## Known Limitations

- Similarity threshold tuned by eye on one subject, not statistically calibrated
- Coverage limited to what Yandex has indexed; no guarantee for low-footprint people
- Apify/Yandex terms may restrict production use beyond this demo
- Not GDPR/DPDP compliant — demo-only
