# How to Rotate the API Key

**Mode: How-to.**

This guide explains how to rotate the read-only Coinbase API key that
Acervator uses for portfolio queries.

## Prerequisites

- Coinbase account with view-only API access
- Write access to `~/.acervator/coinbase_credentials.json`
- Acervator not currently running (or you accept a brief read failure)

## Steps

1. Sign in to Coinbase and open API Management.
2. Create a new view-only key. Save the secret before you close the tab.
3. Stop Acervator if it is running.
4. Open `~/.acervator/coinbase_credentials.json` in a text editor.
5. Replace the `api_key` and `api_secret` values with the new pair.
6. Save the file. Set its permissions to owner-read-write only.
7. Restart Acervator. Confirm the balance display updates within one minute.
8. Revoke the old key in Coinbase API Management.

## Verify

Watch `~/.acervator_logs/trade.log` for a successful balance fetch entry
within one minute of restart. If no entry appears, the new key is not
authenticating; check the JSON file for a typo before revoking the old key.

## Rollback

If the new key fails, paste the old key back into the JSON file and
restart Acervator. The old key remains valid until you revoke it in
Coinbase.
