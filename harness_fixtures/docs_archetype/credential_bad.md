# Venue Sign-In Values

Reference. One page carrying a credential in each shape DOC014 names, so the
rule reports every row and the page cannot be green.

## The labelled secret and the passphrase

The two fields a venue answers with, written out in full.

```
api_secret: 9f3Ab7Qz1XpL0eRtYu2WsVn4Mk8Jh6Gd5Fc3Bv1Nz
passphrase = Tr0ubad0ur-Hinge-Vault-71
```

## The bearer token one broker issues

The header a broker request carries after a sign-in.

```
Authorization: Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.aGFybmVzc2JvZHk
```

## The private key block

The armour and a body, as a text field receives it.

```
-----BEGIN EC PRIVATE KEY-----
MHcCAQEEIKxQq7Yd3Jm2Vp9Lc5Rn8Te1Wh4Gb6Sa0Xf2Zu7Nv3DoAoGCCqGSM49
-----END EC PRIVATE KEY-----
```

## The hex private key

The value a deployment reads out of its environment.

```
0x4c0883a69102937d6231471b5dbb6204fe512961708279a9f2e4d3b7c1a85e6f
```

## The Coinbase key name

The long form a CDP key takes, both halves filled in.

```
organizations/7b1d2c3e-4f5a-6b7c-8d9e-0a1b2c3d4e5f/apiKeys/9a8b7c6d-5e4f-3a2b-1c0d-9e8f7a6b5c4d
```

## The connection string

A store address carrying its own password.

```
postgres://ledger_writer:Hv7Qn2Ls9Tz4@db.example.invalid:5432/ledger
```

Every block above holds a credential this body invents. Six shapes are
written, so DOC014 reports seven rows and the page exits non-zero.
