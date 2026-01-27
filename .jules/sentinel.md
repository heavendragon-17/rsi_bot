## 2026-01-27 - Missing Log Redaction
**Vulnerability:** The application was logging environment variables in plain text via the default `logging.Formatter`.
**Learning:** Even if `RedactingFormatter` is mentioned in documentation or memory, it must be verified in the actual codebase. Assumptions about existing security controls can be dangerous.
**Prevention:** Implement automated tests that specifically attempt to log secrets and verify they are redacted.
