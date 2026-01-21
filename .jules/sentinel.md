## 2026-01-21 - Missing Sensitive Data Redaction in Logger
**Vulnerability:** The logging system lacked the `RedactingFormatter` claimed in documentation/memory, causing potential leakage of environment variables (API keys, secrets) if logged.
**Learning:** Documentation or "memory" of security features is not proof of existence. Always verify implementation against the codebase.
**Prevention:** Implemented `RedactingFormatter` to automatically strip values of sensitive environment variables (keys, secrets, tokens) from all log records. Added `tests/test_security_logger.py` to enforce this.
