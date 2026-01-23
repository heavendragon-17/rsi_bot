## 2026-01-23 - Missing RedactingFormatter
**Vulnerability:** The logging system was missing the `RedactingFormatter` which was documented/expected to exist. This could lead to sensitive environment variables (API keys, passwords) being logged in plain text.
**Learning:** Security features described in documentation or memory must be verified in code. Do not assume existence.
**Prevention:** Implement automated tests that specifically attempt to leak secrets into logs and verify they are redacted. Added `tests/test_security_logger.py` for this purpose.
