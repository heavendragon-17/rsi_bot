## 2026-01-25 - [Log Secret Leakage]
**Vulnerability:** The application was using a standard `logging.Formatter` which logs messages exactly as received. If environment variables or configuration objects containing secrets were logged (e.g., during startup or error handling), sensitive data would be written to `bot.log` in plaintext.
**Learning:** Standard Python logging does not sanitize output by default. Any application handling financial secrets must assume that logs will eventually be viewed by unauthorized parties or stored insecurely.
**Prevention:** Implemented a custom `RedactingFormatter` in `app/utils/logger.py` that automatically scans `os.environ` for keys like 'SECRET', 'KEY', 'TOKEN' and redacts their values from all log messages.
