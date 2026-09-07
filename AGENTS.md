# Shared Standards — faceid-chain-verify
- Python 3.11, type hints on every function signature
- Secrets via python-dotenv + .env only
- No bare except — catch specific exceptions
- Every stage function returns a plain dict
- Print clear "[STAGE] ..." progress lines — this is what gets recorded on camera
- Never print a full embedding vector to stdout — print only scores/lengths
- Candidates filtered to: instagram.com, x.com, twitter.com, linkedin.com, facebook.com, pinterest.com