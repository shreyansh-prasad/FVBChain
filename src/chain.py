import json
import os
import sys
from pathlib import Path

from dotenv import load_dotenv
from web3 import Web3  # pyrefly: ignore [missing-import]
from web3.exceptions import ContractLogicError  # pyrefly: ignore [missing-import]

# Import UTIL layer — do not duplicate pin_json logic
sys.path.insert(0, str(Path(__file__).parent))
from ipfs_utils import pin_json

# ── Load .env from project root (one level up from src/) ──────────────────────
_ROOT = Path(__file__).parent.parent
load_dotenv(_ROOT / ".env")

SEPOLIA_RPC_URL    = os.getenv("SEPOLIA_RPC_URL", "")
WALLET_PRIVATE_KEY = os.getenv("WALLET_PRIVATE_KEY", "")
CONTRACT_ADDRESS   = os.getenv("CONTRACT_ADDRESS", "")
_ABI_PATH          = _ROOT / "abi" / "FaceVerificationRegistry.json"


# ── Helpers ───────────────────────────────────────────────────────────────────

def _load_abi() -> list:
    """Reads ABI from file — never hardcoded."""
    if not _ABI_PATH.exists():
        raise FileNotFoundError(
            f"ABI not found at {_ABI_PATH}. "
            "Complete the Remix deployment first."
        )
    with open(_ABI_PATH) as fh:
        return json.load(fh)


def _check_env() -> None:
    """Stops early with a clear message if any required env var is missing."""
    missing = [k for k, v in {
        "SEPOLIA_RPC_URL":    SEPOLIA_RPC_URL,
        "WALLET_PRIVATE_KEY": WALLET_PRIVATE_KEY,
        "CONTRACT_ADDRESS":   CONTRACT_ADDRESS,
    }.items() if not v]
    if missing:
        raise EnvironmentError(
            f"[STAGE] chain: Missing env vars: {missing}. "
            "Add them to .env and retry."
        )


# ── Public API ────────────────────────────────────────────────────────────────

def get_contract():
    """
    Connects to Sepolia via SEPOLIA_RPC_URL and returns the contract instance.
    Raises EnvironmentError if env vars are missing.
    Raises ConnectionError if the node is unreachable.
    """
    _check_env()
    w3 = Web3(Web3.HTTPProvider(SEPOLIA_RPC_URL))
    if not w3.is_connected():
        raise ConnectionError(
            f"[STAGE] chain: Cannot connect to {SEPOLIA_RPC_URL}. "
            "Check SEPOLIA_RPC_URL and network access."
        )
    address = Web3.to_checksum_address(CONTRACT_ADDRESS)
    abi = _load_abi()
    contract = w3.eth.contract(address=address, abi=abi)
    print(f"[STAGE] chain: Connected. Contract at {address}")
    return w3, contract


def submit_record(evidence: dict) -> dict:
    """
    Pins evidence JSON to IPFS, then submits its keccak256 hash + CID
    to the FaceVerificationRegistry contract on Sepolia.

    Returns {"tx_hash", "data_hash", "cid", "explorer_url"} on success.
    Raises ContractLogicError (with revert reason) if the hash already exists.
    Raises EnvironmentError if Sepolia ETH is insufficient.
    """
    print("[STAGE] chain: Pinning evidence JSON to IPFS ...")
    pin_result = pin_json(evidence)
    if "error" in pin_result:
        raise RuntimeError(f"[STAGE] chain: IPFS pin failed — {pin_result}")
    cid = pin_result["cid"]
    print(f"[STAGE] chain: Evidence CID = {cid}")

    # Deterministic hash — sort_keys ensures identical dicts hash identically
    canonical = json.dumps(evidence, sort_keys=True)
    data_hash: bytes = Web3.keccak(text=canonical)
    print(f"[STAGE] chain: data_hash = {data_hash.hex()}")

    w3, contract = get_contract()
    account = w3.eth.account.from_key(WALLET_PRIVATE_KEY)

    # Check balance before attempting tx — surface insufficient-funds early
    balance_wei = w3.eth.get_balance(account.address)
    print(f"[STAGE] chain: Wallet {account.address} balance = {w3.from_wei(balance_wei, 'ether'):.6f} ETH")
    if balance_wei == 0:
        raise EnvironmentError(
            "[STAGE] chain: STOP — wallet has 0 ETH on this network. "
            "Fund via an Alchemy or QuickNode Sepolia faucet before retrying."
        )

    # Build tx — let web3.py estimate gas, don't hardcode
    print("[STAGE] chain: Building and signing transaction ...")
    try:
        tx = contract.functions.submitRecord(data_hash, cid).build_transaction({
            "from": account.address,
            "nonce": w3.eth.get_transaction_count(account.address),
        })
    except ContractLogicError as e:
        # Surface the revert reason verbatim — likely "Record already exists"
        print(f"[STAGE] chain: Contract reverted during gas estimation — {e}")
        raise

    signed = w3.eth.account.sign_transaction(tx, WALLET_PRIVATE_KEY)
    tx_hash_hex = w3.eth.send_raw_transaction(signed.raw_transaction).hex()
    print(f"[STAGE] chain: Tx sent. Hash = {tx_hash_hex}")
    print(f"[STAGE] chain: Waiting for receipt ...")

    receipt = w3.eth.wait_for_transaction_receipt(tx_hash_hex, timeout=120)
    if receipt["status"] != 1:
        raise RuntimeError(
            f"[STAGE] chain: Transaction reverted on-chain. "
            f"Receipt: {receipt}"
        )

    explorer_url = f"https://sepolia.etherscan.io/tx/{tx_hash_hex}"
    print(f"[STAGE] chain: [OK] Confirmed in block {receipt['blockNumber']}")
    print(f"[STAGE] chain: Explorer: {explorer_url}")

    return {
        "tx_hash":     tx_hash_hex,
        "data_hash":   data_hash.hex(),
        "cid":         cid,
        "explorer_url": explorer_url,
    }


def verify_record(data_hash: bytes) -> dict:
    """
    Calls the read-only verifyRecord() on the contract.
    Returns {"exists", "timestamp", "cid", "submitter"}.
    data_hash may be raw bytes or a 0x-prefixed hex string.
    """
    # Accept hex string as convenience
    if isinstance(data_hash, str):
        data_hash = bytes.fromhex(data_hash.removeprefix("0x"))

    _, contract = get_contract()
    exists, timestamp, cid, submitter = contract.functions.verifyRecord(data_hash).call()
    print(f"[STAGE] chain: verifyRecord -> exists={exists}, timestamp={timestamp}, submitter={submitter}")
    return {
        "exists":    exists,
        "timestamp": timestamp,
        "cid":       cid,
        "submitter": submitter,
    }


def demo_tamper(evidence: dict) -> None:
    """
    Hashes a subtly modified copy of evidence and confirms the contract
    returns exists=False — proving tamper-detection works.
    """
    print("\n[STAGE] chain: === Tamper Demo ===")
    # Flip one field — the hash will differ from the submitted record
    tampered = {**evidence, "_tampered": True}
    tampered_canonical = json.dumps(tampered, sort_keys=True)
    tampered_hash: bytes = Web3.keccak(text=tampered_canonical)
    print(f"[STAGE] chain: Tampered data_hash = {tampered_hash.hex()}")

    result = verify_record(tampered_hash)
    if result["exists"]:
        print("[STAGE] chain: WARNING: UNEXPECTED — tampered hash returned exists=True!")
    else:
        print("[STAGE] chain: [OK] Tamper detected - exists=False as expected.")
    print(f"[STAGE] chain: Full tamper result: {result}")


if __name__ == "__main__":
    import time
    # End-to-end demo: submit -> verify (real) -> verify (tampered)
    sample_evidence = {
        "subject": "demo",
        "model":   "Facenet512",
        "note":    "standalone chain.py test",
        "timestamp": time.time(),
    }

    canonical = json.dumps(sample_evidence, sort_keys=True)
    data_hash: bytes = Web3.keccak(text=canonical)

    print("[STAGE] chain: --- Submit ---")
    try:
        record = submit_record(sample_evidence)
        print(f"[STAGE] chain: Submit result: tx_hash={record['tx_hash']}")
        print(f"[STAGE] chain: Explorer: {record['explorer_url']}")
    except ContractLogicError as e:
        print(f"[STAGE] chain: Contract reverted - {e}")
        print("[STAGE] chain: If 'Record already exists', verifying existing record...")
    except (EnvironmentError, ConnectionError) as e:
        print(str(e))
        sys.exit(1)

    print("\n[STAGE] chain: --- Verify (real hash) ---")
    real_result = verify_record(data_hash)
    print(f"[STAGE] chain: Verify result: {real_result}")

    demo_tamper(sample_evidence)
