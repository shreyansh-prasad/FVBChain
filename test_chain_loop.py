import time
import sys
from src.chain import submit_record, verify_record, demo_tamper
from web3 import Web3
from web3.exceptions import ContractLogicError

def main():
    print("Running 3x back-to-back chain tests...\n")
    for i in range(1, 4):
        print(f"=== TEST RUN {i}/3 ===")
        evidence = {
            "test_run": i,
            "timestamp": time.time(),
            "note": "Back-to-back verification test"
        }
        
        try:
            # 1. Submit
            record = submit_record(evidence)
            print(f"[{i}] Submit SUCCESS: {record['explorer_url']}")
            
            # 2. Verify
            print(f"[{i}] Verifying hash: {record['data_hash']}")
            data_hash_bytes = bytes.fromhex(record["data_hash"])
            v_res = verify_record(data_hash_bytes)
            print(f"[{i}] Verify SUCCESS -> exists: {v_res['exists']}")
            
            # 3. Tamper
            demo_tamper(evidence)
            print("\n")
            
        except Exception as e:
            print(f"[{i}] FAILED: {e}")
            sys.exit(1)
            
    print("All 3 test runs completed successfully!")

if __name__ == "__main__":
    main()
