"""KeyringManager.delete must name the key it failed on, and CredentialVault
must round-trip a credential that carries no exchange passphrase.

``delete`` logs through ``logger``; ``CredentialVault.store`` and
``CredentialVault.retrieve`` wrap ``encrypt`` and ``decrypt``.
"""

from src.core.encryption import CredentialVault, KeyringManager

_MASTER_INPUT = "unit-test-" + "master-input"
_KEY_INPUT = "key-" + "material"
_SECRET_INPUT = "api-" + "material"
_EXTRA_INPUT = "exchange-side-" + "value"


class _RaisingKeyring:
    """Stands in for the ``keyring`` module and fails every delete_password call."""

    def __init__(self) -> None:
        self.calls: list[tuple[str, str]] = []

    def delete_password(self, service: str, username: str) -> None:
        self.calls.append((service, username))
        raise RuntimeError("backend refused")


def test_delete_logs_the_username_it_failed_on(capture_log) -> None:
    manager = KeyringManager(allow_insecure_memory_fallback=True)
    fake = _RaisingKeyring()
    manager._kr = fake

    with capture_log("acervator.encryption") as records:
        manager.delete("coinbase-master")

    assert fake.calls == [
        ("acervator", "coinbase-master")
    ], f"delete must reach the backend; got {fake.calls!r}"
    text = "\n".join(r.getMessage() for r in records)
    assert "coinbase-master" in text, (
        "the debug line must name the key that failed, not a placeholder; "
        f"got {text!r}"
    )
    assert "'?'" not in text, f"a literal placeholder reached the log; got {text!r}"


def test_delete_log_carries_no_version_string(capture_log) -> None:
    manager = KeyringManager(allow_insecure_memory_fallback=True)
    manager._kr = _RaisingKeyring()

    with capture_log("acervator.encryption") as records:
        manager.delete("some-key")

    text = "\n".join(r.getMessage() for r in records)
    assert text, "positive control: the failure must produce a log record"
    assert "v3." not in text, f"a version string reached the log; got {text!r}"


def test_vault_round_trips_a_credential_with_no_exchange_passphrase() -> None:
    vault = CredentialVault(_MASTER_INPUT)
    vault.store("testex", api_key=_KEY_INPUT, api_secret=_SECRET_INPUT)

    key, secret, extra = vault.retrieve("testex")

    assert key == _KEY_INPUT, f"api_key must round-trip; got {key!r}"
    assert secret == _SECRET_INPUT, f"api_secret must round-trip; got {secret!r}"
    assert extra == "", f"an absent passphrase decrypts to empty; got {extra!r}"


def test_vault_round_trips_an_exchange_passphrase_when_given() -> None:
    vault = CredentialVault(_MASTER_INPUT)
    vault.store(
        "testex",
        api_key=_KEY_INPUT,
        api_secret=_SECRET_INPUT,
        passphrase=_EXTRA_INPUT,
    )

    _key, _secret, extra = vault.retrieve("testex")

    assert extra == _EXTRA_INPUT, (
        "a supplied passphrase must round-trip, proving the previous test's "
        f"empty string is not a blanket zero; got {extra!r}"
    )
