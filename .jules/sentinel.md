## 2026-01-26 - Missing RedactingFormatter
**Vulnerability:** The application was logging sensitive data without redaction because `RedactingFormatter` was missing despite being mentioned in documentation/memory.
**Learning:** Security controls (like redacting loggers) must be verified in code, not just assumed from documentation or memory. Regression tests for security features are essential to prevent them from being silently dropped.
**Prevention:** Added `tests/test_security_logger.py` to enforce redaction logic.
