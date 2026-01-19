## 2025-02-18 - Secrets in Exception Logs
**Vulnerability:** Private keys (Lighter DEX) were leaked in logs when exceptions occurred during client initialization or API calls, because the exception message (e.g. from `lighter-python`) contained the sensitive arguments.
**Learning:** Libraries often include argument values in their exception messages. Simply logging `e` is insecure when secrets are passed as arguments.
**Prevention:** Always sanitize exception messages before logging them in contexts where secrets are handled. Use a helper like `_sanitize_log_message`.
