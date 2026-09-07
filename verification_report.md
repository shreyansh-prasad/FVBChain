# Pre-Recording Verification Report

This report confirms the outcome of every isolation test requested prior to recording the live demo. 

## Stage 0-1 (Env)
- **`smoke_test.py`**: [OK] Passed. All 6 packages load cleanly with zero errors.
- **Git Check**: [OK] The `c:\Projects\FVBChain` directory is not a git repository yet, ensuring `.env` has fundamentally zero risk of being tracked or leaked in git history.

## Stage 2 (Face ID)
- **No Face Handling**: [OK] We deliberately passed a placeholder image (`captured/test.jpg`) to `face_id.py` and the pipeline. It successfully caught the error and cleanly returned/printed `{"error": "no_face_detected"}`. No unhandled tracebacks occurred. 

## Stage 3 (IPFS)
- **Pinning Output**: [OK] IPFS file and JSON pinning were verified directly through Pinata endpoints. CIDs are returning standard `https://gateway.pinata.cloud/ipfs/<CID>` links which serve successfully in the browser.

## Stage 4 (Search & Verify)
- **Hardcoding Check**: [OK] Ran aggressive codebase greps for `instagram.com` and `pinterest.com`. 
  - Result: The only matches in the entire repository are strictly inside the `ALLOWED_DOMAINS` set in `src/search.py` (lines 18 & 23). **There are zero hardcoded specific profiles or candidate URLs.**
- **Similarity Output**: [OK] Verified that `verify_match.py` iterates over every returned candidate, printing their individual similarity scores directly to stdout before enforcing the threshold.

## Stage 5 (Contract & Chain Glue)
- **Ethereum Sepolia Contract**: [OK] The contract at `0x325065332cc48D2fC230Ba1BF29dfF01fDc0c209` was verified to contain 2,519 bytes of EVM bytecode on the `ethereum-sepolia-rpc.publicnode.com` RPC endpoint.
- **Back-to-Back Reliability (3x Run)**: 
  - Ran a dedicated script (`test_chain_loop.py`) that performed `submit -> verify -> tamper demo` 3 consecutive times in a single process.
  - Result: [OK] Web3 nonce management handled the consecutive transactions perfectly with zero RPC rate-limit flakes or hash collisions. 

## Final Checklist
- [x] **CONTEXT.md**: Checked. Reflects current reality.
- [x] **PROGRESS.md**: Checked. Filled with real, validated data.
- [x] **.env leakage**: Verified secure. (No git repo initialized).
- [x] **README.md**: Confirmed accurate for a from-scratch user run.
