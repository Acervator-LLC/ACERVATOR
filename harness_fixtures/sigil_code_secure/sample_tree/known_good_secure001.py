# SECURE001: _redact in src/exchange/api_logger.py since commit a703c497, holding all nine words

REDACTED = "***REDACTED***"


def _redact(params: dict) -> dict:
    """Replace every credential-named value in ``params`` with "***REDACTED***"."""
    redacted = {}
    sensitive = {
        "apikey",
        "secret",
        "password",
        "passphrase",
        "key",
        "token",
        "sign",
        "auth",
        "credential",
    }
    for k, v in params.items():
        if any(s in k.lower() for s in sensitive):
            redacted[k] = REDACTED
        elif isinstance(v, str) and len(v) > 50:
            redacted[k] = v[:20] + "..."
        else:
            redacted[k] = v
    return redacted
