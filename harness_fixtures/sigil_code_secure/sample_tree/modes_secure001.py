# SECURE001 credential-mask-missing-word: each faulty_ function holds one form of the fault; its
# corrected_ twin holds all nine required words, its purpose_ twin reads the same words for no name
# test, its plain_ twin runs the same test over param names, and its single_ twin over one credential

REDACTED = "***REDACTED***"
MASK = "***"
LONG = 50
SHOWN = 20

TASK30_HIDDEN = (
    "authorization",
    "cookie",
    "apikey",
    "api-key",
    "secret",
    "password",
    "passphrase",
    "token",
)
TASK30_HIDDEN_ALL = (*TASK30_HIDDEN, "key", "sign", "auth", "credential")
TASK30_PARAMS = ("symbol", "side", "type", "amount", "price", "attempt", "order_id", "exchange")
TASK30_ONE = ("token", "symbol", "side", "amount")

LIST_WORDS = ["apikey", "secret", "password", "passphrase", "token", "auth"]
LIST_WORDS_ALL = ["apikey", "secret", "password", "passphrase", "key", "token", "sign", "auth",
                  "credential"]
LIST_PARAMS = ["symbol", "side", "type", "amount", "price", "attempt", "order_id", "exchange"]
LIST_ONE = ["secret", "symbol", "side", "amount"]

FROZEN_WORDS = frozenset({"api_key", "secret", "password", "token", "signature", "credentials"})
FROZEN_WORDS_ALL = frozenset({"apikey", "secret", "password", "passphrase", "key", "token", "sign",
                              "auth", "credential"})
FROZEN_PARAMS = frozenset({"symbol", "side", "type", "amount", "price", "order_id"})
FROZEN_ONE = frozenset({"password", "symbol", "side", "amount"})

NOT_IN_WORDS = ("apikey", "secret", "password", "key", "token", "sign", "auth")
NOT_IN_WORDS_ALL = ("apikey", "secret", "password", "passphrase", "key", "token", "sign", "auth",
                    "credential")
NOT_IN_PARAMS = ("symbol", "side", "type", "amount", "price", "attempt")
NOT_IN_ONE = ("auth", "symbol", "side", "amount")

DENY_WORDS = ["password", "secret", "api_key", "apikey", "auth", "credentials", "token", "cookie"]
DENY_WORDS_ALL = [*DENY_WORDS, "passphrase", "key", "sign", "credential"]
DENY_PARAMS = ["symbol", "side", "type", "amount", "price", "order_id", "exchange"]
DENY_ONE = ["token", "symbol", "side", "amount"]


# Commit a703c497 fixed this _redact in src/exchange/api_logger.py: "sign", "auth" and
# "credential" were missing, so a param named signature reached the entry unmasked.
def faulty_history_redact(params: dict[str, object]) -> dict[str, object]:
    redacted: dict[str, object] = {}
    sensitive = {"apikey", "secret", "password", "passphrase", "key", "token"}
    for k, v in params.items():
        if any(s in k.lower() for s in sensitive):
            redacted[k] = REDACTED
        elif isinstance(v, str) and len(v) > LONG:
            redacted[k] = v[:SHOWN] + "..."
        else:
            redacted[k] = v
    return redacted


def corrected_history_redact(params: dict[str, object]) -> dict[str, object]:
    redacted: dict[str, object] = {}
    sensitive = {"apikey", "secret", "password", "passphrase", "key", "token", "sign", "auth",
                 "credential"}
    for k, v in params.items():
        if any(s in k.lower() for s in sensitive):
            redacted[k] = REDACTED
        elif isinstance(v, str) and len(v) > LONG:
            redacted[k] = v[:SHOWN] + "..."
        else:
            redacted[k] = v
    return redacted


def purpose_history_redact(params: dict[str, object]) -> list[str]:
    sensitive = {"apikey", "secret", "password", "passphrase", "key", "token"}
    return [field for field in sorted(sensitive) if not params.get(field)]


def plain_history_redact(params: dict[str, object]) -> dict[str, object]:
    redacted: dict[str, object] = {}
    sensitive = {"symbol", "side", "type", "amount", "price", "attempt", "order_id", "exchange"}
    for k, v in params.items():
        if any(s in k.lower() for s in sensitive):
            redacted[k] = REDACTED
        else:
            redacted[k] = v
    return redacted


def single_history_redact(params: dict[str, object]) -> dict[str, object]:
    redacted: dict[str, object] = {}
    sensitive = {"token", "symbol", "side", "amount"}
    for k, v in params.items():
        if any(s in k.lower() for s in sensitive):
            redacted[k] = REDACTED
        else:
            redacted[k] = v
    return redacted


# Experiment 3, task09, api_record.py: the same set, read as name.lower().
def faulty_task09_redact(params: dict[str, object]) -> dict[str, object]:
    redacted: dict[str, object] = {}
    sensitive = {"apikey", "secret", "password", "passphrase", "key", "token"}
    for name, value in params.items():
        if any(word in name.lower() for word in sensitive):
            redacted[name] = REDACTED
        elif isinstance(value, str) and len(value) > LONG:
            redacted[name] = value[:SHOWN] + "..."
        else:
            redacted[name] = value
    return redacted


def corrected_task09_redact(params: dict[str, object]) -> dict[str, object]:
    redacted: dict[str, object] = {}
    sensitive = {"apikey", "secret", "password", "passphrase", "key", "token", "sign", "auth",
                 "credential"}
    for name, value in params.items():
        if any(word in name.lower() for word in sensitive):
            redacted[name] = REDACTED
        else:
            redacted[name] = value
    return redacted


def purpose_task09_redact(params: dict[str, object]) -> str:
    sensitive = {"apikey", "secret", "password", "passphrase", "key", "token"}
    return f"{len(params)} params; masked names: {', '.join(sorted(sensitive))}"


def plain_task09_redact(params: dict[str, object]) -> dict[str, object]:
    redacted: dict[str, object] = {}
    sensitive = {"symbol", "side", "type", "amount", "price", "attempt"}
    for name, value in params.items():
        if any(word in name.lower() for word in sensitive):
            redacted[name] = REDACTED
        else:
            redacted[name] = value
    return redacted


def single_task09_redact(params: dict[str, object]) -> dict[str, object]:
    redacted: dict[str, object] = {}
    sensitive = {"secret", "symbol", "side", "amount"}
    for name, value in params.items():
        if any(word in name.lower() for word in sensitive):
            redacted[name] = REDACTED
        else:
            redacted[name] = value
    return redacted


# Experiment 3, task30, request_trace.py: a module tuple of header words.
def faulty_task30_mask_headers(headers: dict[str, str]) -> dict[str, str]:
    masked: dict[str, str] = {}
    for name, value in headers.items():
        if any(word in name.lower() for word in TASK30_HIDDEN):
            masked[name] = MASK
        elif len(value) > LONG:
            masked[name] = value[:SHOWN] + "..."
        else:
            masked[name] = value
    return masked


def corrected_task30_mask_headers(headers: dict[str, str]) -> dict[str, str]:
    masked: dict[str, str] = {}
    for name, value in headers.items():
        if any(word in name.lower() for word in TASK30_HIDDEN_ALL):
            masked[name] = MASK
        else:
            masked[name] = value
    return masked


def purpose_task30_mask_headers(headers: dict[str, str]) -> list[str]:
    return [f"> {word}: {headers.get(word, '')}" for word in TASK30_HIDDEN]


def plain_task30_mask_headers(headers: dict[str, str]) -> dict[str, str]:
    masked: dict[str, str] = {}
    for name, value in headers.items():
        if any(word in name.lower() for word in TASK30_PARAMS):
            masked[name] = MASK
        else:
            masked[name] = value
    return masked


def single_task30_mask_headers(headers: dict[str, str]) -> dict[str, str]:
    masked: dict[str, str] = {}
    for name, value in headers.items():
        if any(word in name.lower() for word in TASK30_ONE):
            masked[name] = MASK
        else:
            masked[name] = value
    return masked


# A local tuple, and an exact test of a lowered name with in.
def faulty_tuple_local_exact(name: str, value: str) -> str:
    masked_names = ("apikey", "api_key", "secret", "password", "passphrase", "key", "sign")
    if name.lower() in masked_names:
        return MASK
    return value


def corrected_tuple_local_exact(name: str, value: str) -> str:
    masked_names = ("apikey", "api_key", "secret", "password", "passphrase", "key", "token",
                    "sign", "auth", "credential")
    if name.lower() in masked_names:
        return MASK
    return value


def purpose_tuple_local_exact(name: str, value: str) -> str:
    masked_names = ("apikey", "api_key", "secret", "password", "passphrase", "key", "sign")
    return f"{name}={value}; fields: {', '.join(masked_names)}"


def plain_tuple_local_exact(name: str, value: str) -> str:
    masked_names = ("symbol", "side", "type", "amount", "price", "attempt")
    if name.lower() in masked_names:
        return MASK
    return value


def single_tuple_local_exact(name: str, value: str) -> str:
    masked_names = ("key", "symbol", "side", "amount")
    if name.lower() in masked_names:
        return MASK
    return value


# A module list, and a substring test inside any.
def faulty_list_module_any(name: str, value: str) -> str:
    if any(word in name.lower() for word in LIST_WORDS):
        return MASK
    return value


def corrected_list_module_any(name: str, value: str) -> str:
    if any(word in name.lower() for word in LIST_WORDS_ALL):
        return MASK
    return value


def purpose_list_module_any(name: str, value: str) -> dict[str, str]:
    fields = dict.fromkeys(LIST_WORDS, "")
    fields[name] = value
    return fields


def plain_list_module_any(name: str, value: str) -> str:
    if any(word in name.lower() for word in LIST_PARAMS):
        return MASK
    return value


def single_list_module_any(name: str, value: str) -> str:
    if any(word in name.lower() for word in LIST_ONE):
        return MASK
    return value


# A set written in the test itself, and an exact test of a lowered name with in.
def faulty_set_inline_exact(name: str, value: str) -> str:
    if name.lower() in {"apikey", "secret", "password", "passphrase", "token", "signature"}:
        return MASK
    return value


def corrected_set_inline_exact(name: str, value: str) -> str:
    if name.lower() in {"apikey", "secret", "password", "passphrase", "key", "token", "sign",
                        "auth", "credential"}:
        return MASK
    return value


def purpose_set_inline_exact(name: str, value: str) -> str:
    known = sorted({"apikey", "secret", "password", "passphrase", "token", "signature"})
    return f"{name}={value} of {len(known)} fields"


def plain_set_inline_exact(name: str, value: str) -> str:
    if name.lower() in {"symbol", "side", "type", "amount", "price", "exchange"}:
        return MASK
    return value


def single_set_inline_exact(name: str, value: str) -> str:
    if name.lower() in {"passphrase", "symbol", "side", "amount"}:
        return MASK
    return value


# A module frozenset, and an exact test of a lowered name with in.
def faulty_frozenset_module_exact(name: str, value: str) -> str:
    if name.lower() in FROZEN_WORDS:
        return MASK
    return value


def corrected_frozenset_module_exact(name: str, value: str) -> str:
    if name.lower() in FROZEN_WORDS_ALL:
        return MASK
    return value


def purpose_frozenset_module_exact(name: str, value: str) -> str:
    return f"{name}={value}; {len(FROZEN_WORDS)} masked fields"


def plain_frozenset_module_exact(name: str, value: str) -> str:
    if name.lower() in FROZEN_PARAMS:
        return MASK
    return value


def single_frozenset_module_exact(name: str, value: str) -> str:
    if name.lower() in FROZEN_ONE:
        return MASK
    return value


# A local frozenset, and a substring test inside any.
def faulty_frozenset_local_any(name: str, value: str) -> str:
    words = frozenset(("apikey", "secret", "passphrase", "key", "token", "sign", "credential"))
    if any(word in name.lower() for word in words):
        return MASK
    return value


def corrected_frozenset_local_any(name: str, value: str) -> str:
    words = frozenset(("apikey", "secret", "password", "passphrase", "key", "token", "sign",
                       "auth", "credential"))
    if any(word in name.lower() for word in words):
        return MASK
    return value


def purpose_frozenset_local_any(name: str, value: str) -> list[str]:
    words = frozenset(("apikey", "secret", "passphrase", "key", "token", "sign", "credential"))
    return [f"{word}={value}" for word in sorted(words) if word != name]


def plain_frozenset_local_any(name: str, value: str) -> str:
    words = frozenset(("symbol", "side", "type", "amount", "price", "order_id"))
    if any(word in name.lower() for word in words):
        return MASK
    return value


def single_frozenset_local_any(name: str, value: str) -> str:
    words = frozenset(("credential", "symbol", "side", "amount"))
    if any(word in name.lower() for word in words):
        return MASK
    return value


# A list written as the iterable any reads, and a substring test.
def faulty_list_inline_any(name: str, value: str) -> str:
    if any(word in name.lower() for word in ["apikey", "secret", "password", "key", "token"]):
        return MASK
    return value


def corrected_list_inline_any(name: str, value: str) -> str:
    if any(word in name.lower() for word in ["apikey", "secret", "password", "passphrase",
                                               "key", "token", "sign", "auth", "credential"]):
        return MASK
    return value


def purpose_list_inline_any(name: str, value: str) -> str:
    return f"{name}={value}; " + ", ".join(["apikey", "secret", "password", "key", "token"])


def plain_list_inline_any(name: str, value: str) -> str:
    if any(word in name.lower() for word in ["symbol", "side", "type", "amount", "price"]):
        return MASK
    return value


def single_list_inline_any(name: str, value: str) -> str:
    if any(word in name.lower() for word in ["sign", "symbol", "side", "amount"]):
        return MASK
    return value


# A module tuple, and an exact test with not in.
def faulty_tuple_module_not_in(name: str, value: str) -> str:
    return value if name.lower() not in NOT_IN_WORDS else MASK


def corrected_tuple_module_not_in(name: str, value: str) -> str:
    return value if name.lower() not in NOT_IN_WORDS_ALL else MASK


def purpose_tuple_module_not_in(name: str, value: str) -> str:
    return f"{name}={value}; first masked field {NOT_IN_WORDS[0]}"


def plain_tuple_module_not_in(name: str, value: str) -> str:
    return value if name.lower() not in NOT_IN_PARAMS else MASK


def single_tuple_module_not_in(name: str, value: str) -> str:
    return value if name.lower() not in NOT_IN_ONE else MASK


# A local tuple, and a substring test inside all.
def faulty_tuple_local_all(name: str, value: str) -> str:
    words = ("apikey", "secret", "password", "passphrase", "token", "auth", "credential")
    if all(word not in name.lower() for word in words):
        return value
    return MASK


def corrected_tuple_local_all(name: str, value: str) -> str:
    words = ("apikey", "secret", "password", "passphrase", "key", "token", "sign", "auth",
             "credential")
    if all(word not in name.lower() for word in words):
        return value
    return MASK


def purpose_tuple_local_all(name: str, value: str) -> str:
    words = ("apikey", "secret", "password", "passphrase", "token", "auth", "credential")
    return f"{name}={value}; {words.count(name)} matching field"


def plain_tuple_local_all(name: str, value: str) -> str:
    words = ("symbol", "side", "type", "amount", "price", "attempt")
    if all(word not in name.lower() for word in words):
        return value
    return MASK


def single_tuple_local_all(name: str, value: str) -> str:
    words = ("apikey", "symbol", "side", "amount")
    if all(word not in name.lower() for word in words):
        return value
    return MASK


# The Sentry SDK form, sentry_sdk/scrubber.py: an exact test of a key lowered with "-" turned
# to "_", against a module list.
def faulty_normalized_exact(name: str, value: str) -> str:
    if name.lower().replace("-", "_") in DENY_WORDS:
        return MASK
    return value


def corrected_normalized_exact(name: str, value: str) -> str:
    if name.lower().replace("-", "_") in DENY_WORDS_ALL:
        return MASK
    return value


def purpose_normalized_exact(name: str, value: str) -> dict[str, str]:
    return {word.upper(): value for word in DENY_WORDS if word != name}


def plain_normalized_exact(name: str, value: str) -> str:
    if name.lower().replace("-", "_") in DENY_PARAMS:
        return MASK
    return value


def single_normalized_exact(name: str, value: str) -> str:
    if name.lower().replace("-", "_") in DENY_ONE:
        return MASK
    return value
