# The project age rule — what each run printed, and the one defect found

Reference. Subjects: `src/competition/project_age.py`,
`src/competition/__init__.py`,
`docs/manual/08-tabs/proof-of-accumulation.md`.

Every run below used `python -X dev -X faulthandler` with `PYTHONWARNINGS=error`.
No test was written. No trading arithmetic was touched. `main.py` was never
launched: `main.py:812` builds an instance guard whose `take_ownership` writes
into the runtime folder, and the operator is trading on this machine, so the
construction path was reached through the import that `SharedTestnetBridge`
itself runs.

## The error

One program error, found by running the real code against the real endpoint.

```
python -X dev -X faulthandler -c "... ProjectAgeLookup(...).verdict_for('BTC/USD') ..."
PYTHONWARNINGS=error

Exception ignored while calling deallocator
  <function _TemporaryFileCloser.__del__ at 0x0000015654692510>:
Traceback (most recent call last):
  File ".../Lib/tempfile.py", line 484, in __del__
    _warnings.warn(self.warn_message, ResourceWarning)
ResourceWarning: Implicitly cleaning up <HTTPError 429: 'Too Many Requests'>
ResourceWarning: unclosed <ssl.SSLSocket [closed] fd=548, ...>
```

## Reproduction

```
cd <repo>
PYTHONWARNINGS=error python -X dev -X faulthandler -c \
  "from src.competition.project_age import ProjectAgeLookup, ProjectAgeError
   look = ProjectAgeLookup(cache_path='<scratch>/U8_404_cache.json')
   try:
       look.genesis_date_for('no-such-project-id')
   except ProjectAgeError as exc:
       print(exc)"
```

The identifier does not exist, so CoinGecko answers HTTP 404 and the same path
runs. Any non-200 answer reproduces it.

## The cause

`urllib.error.HTTPError` is a file-like object holding the response body.
`ProjectAgeLookup.genesis_date_for` caught it, raised `ProjectAgeError` from it,
and never closed it. The body stayed open until the interpreter collected it,
and under warnings-as-errors that collection printed two resource warnings and a
traceback from `tempfile`.

```
src/competition/project_age.py  genesis_date_for
  except (OSError, ValueError, TypeError) as exc:
      raise ProjectAgeError(...) from exc      <- the body is still open
```

## The correction

Close the exception's body before raising.

```python
        except (OSError, ValueError, TypeError) as exc:
            # An HTTPError carries an open response body; close releases it.
            closer = getattr(exc, "close", None)
            if callable(closer):
                closer()
            raise ProjectAgeError(
                f"the coin detail call for {coingecko_id} did not answer: {exc}"
            ) from exc
```

`getattr` guards the general case: a plain `OSError` or a `ValueError` from the
JSON decode carries no body to close.

## The rerun

Two-sided. With the close, a 404 prints the refusal and nothing else. With
`closer()` replaced by `pass`, both resource warnings come back.

```
WITH THE CLOSE
  the coin detail call for no-such-project-id did not answer: HTTP Error 404

WITHOUT THE CLOSE
  the coin detail call for no-such-project-id did not answer: HTTP Error 404
  ResourceWarning: unclosed <ssl.SSLSocket [closed] fd=548, ...>
  ResourceWarning: Implicitly cleaning up <HTTPError 404: 'Not Found'>
```

The file was restored with `git checkout --` after the blinding, and the diff is
empty.

## The rule, run against the live endpoint

```
RUN 1  older than six months
  BTC/USD   genesis_date 2009-01-03   meets_age_rule_on 2009-07-03
            reason old_enough    meets_age_rule True
  log line  CoinGecko genesis_date for bitcoin: '2009-01-03'

RUN 2  younger than six months
  BTC/USD asked on 2009-03-01   reason too_young    meets_age_rule False
  BTC/USD asked on 2009-07-02   reason too_young    meets_age_rule False
  BTC/USD asked on 2009-07-03   reason old_enough   meets_age_rule True

RUN 3  no identifier in the asset catalogue
  TRX/USD   coingecko_id ''   reason no_coingecko_id   meets_age_rule False
            no network call, no warning, no exception

RUN 4  CoinGecko answers with no date
  SHIB/USD  coingecko_id 'shiba-inu'   genesis_date ''
            reason no_genesis_date   meets_age_rule False

RUN 5  the call does not answer
  ETH/USD   http_timeout_s 0.001
            reason lookup_failed   meets_age_rule False
  log line  the detail call for ETH/USD did not answer:
            <urlopen error _ssl.c:1063: The handshake operation timed out>
```

A refusal is distinguishable from an error in three ways. It returns a verdict
rather than raising, the verdict names which of the four reasons decided it, and
only `lookup_failed` writes a warning line. A market string that is not a symbol
raises `ProjectAgeError`, and that is the only error path.

## The cache, proved by taking the network away

```
first process, one instance, two lookups of BTC/USD
  one log line:  CoinGecko genesis_date for bitcoin: '2009-01-03'
  both answers:  old_enough

cache file written
  { "genesis_dates": { "bitcoin": "2009-01-03" }, "version": 1 }

second process, http_timeout_s 0.001
  BTC/USD  in the file      old_enough      no log line
  ETH/USD  not in the file  lookup_failed   handshake timed out
```

The second row is the control. In the same process, with the same timeout, a
market absent from the file could not be answered at all, so the Bitcoin answer
cannot have come from a call.

## The four refusal controls

Each refusal was blinded one line at a time, by replacing that branch's reason
with `OLD_ENOUGH`, and restored with `git checkout --`.

| Blinded line | What admitted |
| ------------ | ------------- |
| `reason = NO_COINGECKO_ID` | TRX/USD, meets_age_rule True |
| `reason = TOO_YOUNG` | BTC/USD asked on 2009-03-01, meets_age_rule True |
| `reason = NO_GENESIS_DATE` | SHIB/USD, meets_age_rule True |
| `reason = LOOKUP_FAILED` | ETH/USD with an unreachable host, meets_age_rule True |

After every restore the file measured 9,472 bytes, zero carriage returns, and an
empty diff.

## Construction and reach

`src/gui/main_window.py:277` calls `SharedTestnetBridge.install_on` on every
launch. That method imports a module from the competition package at
`src/gui/shared_testnet.py:151`, which executes the package's own module list,
which now imports the project age module.

```
before: 'src.competition.project_age' in sys.modules  False
from src.competition.local_testnet import LocalTestnet
after : 'src.competition.project_age' in sys.modules  True

ProjectAgeLookup()                <src.competition.project_age.ProjectAgeLookup>
ProjectAgeLookup().cache_path     ~/.acervator/project_genesis_dates.json
```

**Nothing in the running program calls `verdict_for` yet.** The module loads and
the object constructs; the caller arrives with the volume ranking and the market
rotation, which is unit 9.

## The identifier map, and the rate limit

```
crypto_assets.ASSETS                      40 assets, 40 with an identifier
chart_data.COINGECKO_IDS                  40
market_data._COINGECKO_IDS                40 after _load_coingecko_ids
CryptoAsset.launch_year                    10 of 40 filled, a year not a date
markets the eligibility rule reaches       up to 300
```

The lookup resolves from the asset catalogue, which the second map is built from
and the third is a hand-kept copy of. No fourth map was added.

Asked forty times at two seconds apart, the detail endpoint refused thirty-four
calls with HTTP 429. That is a fact about a loop, not about the lookup, which
makes one call per project and then reads the file on every later ask. Pacing
belongs in the loop that walks a venue.

## Nine projects answered, and seven carry no date

```
a date    bitcoin 2009-01-03, chainlink 2017-09-16
no date   uniswap, shiba-inu, pepe, aave, thorchain, the-sandbox, sei-network
no answer 34 calls refused with HTTP 429
```

The thirty-four are a fact about the rate limit and say nothing about those
assets. Of the nine that answered, seven carry no date and are refused.

## Instruments, each proved two-sided once

```
coding_archetype  known_good exit 0   known_bad exit 1
ta_archetype      known_good_ta001 exit 0   known_bad_ta001 exit 1
docs_archetype    known_good.md exit 0   known_bad.md exit 1
```

## Verdicts

```
python -m tools.local_ci --lane black    VERDICT: PASSED
python -m tools.local_ci --lane flake8   VERDICT: PASSED

coding_archetype src/competition/project_age.py   passed True
ta_archetype     src/competition/project_age.py   passed True
coding_archetype src/competition/__init__.py      passed True
docs_archetype   docs/manual/08-tabs/proof-of-accumulation.md   passed True
docs_archetype   tests/debug_reports/2026-09-09_unit08_project_age.md             passed True
```
