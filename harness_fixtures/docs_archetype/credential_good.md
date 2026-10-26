# Venue Sign-In Fields

Reference. One page carrying the near-miss shapes DOC014 must not report, so
the page stays green while the rule runs over it.

## The field names on their own

A venue answers with three fields. Naming a field is not writing its value.

```
api_key
api_secret
passphrase
```

## The placeholder a field shows before a paste

The sign-in field shows the long form a CDP key takes, with both halves left
out.

```
organizations/.../apiKeys/...
```

## The placeholder a deployment prints

The deployment reads the key out of the environment and names it in its own
usage text.

```
export ACERVATOR_PRIVATE_KEY=0xYOUR_PRIVATE_KEY
```

## The value the log writes in place of a secret

Every credential-named value is masked before it reaches a log line.

```
api_secret: ***REDACTED***
```

## The path the vault is stored at

The sealed store sits under the home directory, and its name is not its
contents.

```
.acervator/ata_spm_credentials.json
```

## The short value a field refuses

A field holding four characters is a fragment, not a secret.

```
api_key = 7Q4Z
```

## The documented example key

A published example is not a live credential.

```
api_key = AKIDEXAMPLE7Q4ZB2VN8TJWR6MSLC
```

## The prose that names a password

A sentence about a password carries no password, and the word after the colon
is an ordinary word.

```
password: the one the operator typed at the wizard
```

Every block above is a name, a placeholder, a path, a fragment or a sentence.
None is a credential, so DOC014 reports no row and the page exits zero.
