# SECURE001: _redact in src/exchange/api_logger.py before commit a703c497, unchanged


def _redact(params: dict) -> dict:
    """Redact sensitive values (keys, secrets) from params dict."""
    redacted = {}
    sensitive = {"apikey", "secret", "password", "passphrase", "key", "token"}
    for k, v in params.items():
        if any(s in k.lower() for s in sensitive):
            redacted[k] = "***REDACTED***"
        elif isinstance(v, str) and len(v) > 50:
            redacted[k] = v[:20] + "..."
        else:
            redacted[k] = v
    return redacted
