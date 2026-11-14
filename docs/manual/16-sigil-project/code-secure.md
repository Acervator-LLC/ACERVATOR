# CODE.SECURE@1

Reference. CODE.SECURE@1 reads one Python file with two security scanners,
bandit and semgrep, and reads each finding against the weakness id the scanner
reports for it. The Coding Archetype owns it. It is one sigil of
[the sigil project](../16-sigil-project.md).

## Function and disciplines

CODE.SECURE@1 reads each call, query, secret, parse and path for a weakness an
attacker can use, with the CWE id each tool attaches to it. It draws on one
discipline: security.

Its scope is each bandit test and semgrep rule the house holds: the 75 tests
bandit lists and the 216 rules its two semgrep rule sets give. Security houses
every one, so the card can run 291 rules and leaves none off.
[The tool scope](../16-sigil-project.md#the-tool-scope) states how a rule is
held.

`dev_harness/sigils/code_secure.py, in BANDIT` and `in SEMGREP`:

```python
DISCIPLINES = ("security",)
BANDIT = hold("bandit", house_rules("bandit"), DISCIPLINES)
SEMGREP = hold("semgrep", house_rules("semgrep"), DISCIPLINES)
```

## What it reads

One input line names a Python file, or one function or class in that file.
Tiers 1 and 2 come from the Coding Archetype's input module, and this sigil
adds no condition to tier 2. Tier 3 runs each scanner whose rules the selection keeps, with the rule sets the
coding archetype runs. Bandit runs only the selected tests, and semgrep skips
each rule of the card that the selection leaves out. For a function or class, only the findings inside its
lines count.

A finding counts only under a rule the card holds and the selection keeps. A rule the registry adds
after the house counted its rules is outside the scope, and its finding moves
no verdict.

Each finding carries the CWE id that its own tool reports, or no CWE when the
tool reports none. semgrep downloads both of its rule sets from its registry on
each run. A tool that exits with any other code, reports an error, or did not
read the file stops the run.

Semgrep runs with `--timeout=0`, so no rule stops at a per-rule time limit.
Semgrep's own default limit is 5 seconds a rule. The OCIR case C1 restores the
828,372-byte `src/trading/scrumming_bot.py` from before its fix. On a quiet
machine, with RAM between 38 and 42 percent, one or two rules passed that
default on that file in each run, and the sigil refused the file. With no
per-rule limit, the same file reads in 36 seconds, and its slowest rule,
dangerous-system-call-tainted-env-args, takes 13 seconds. The whole semgrep run
keeps its 180-second limit, which stops a run that hangs.

`dev_harness/sigils/code_secure.py, in SEMGREP_NO_RULE_TIMEOUT`:

```python
SEMGREP_TIMEOUT_S = 180
SEMGREP_NO_RULE_TIMEOUT = "--timeout=0"
```

`dev_harness/sigils/code_secure.py, in BANDIT_SEVERITY` and `in SEMGREP_SEVERITY`,
the grades each tool's severity takes:

```python
SEVERITIES = ("low", "medium", "high")
BANDIT_SEVERITY = {"LOW": "low", "MEDIUM": "medium", "HIGH": "high"}
SEMGREP_SEVERITY = {"INFO": "low", "WARNING": "medium", "ERROR": "high"}
```

`dev_harness/sigils/code_secure.py, in findings`, the findings that
count:

```python
    kept = [
        finding
        for finding in found
        if f"{finding.tool} {finding.rule}" in to_run
        and (not is_narrowed or first <= finding.line <= last)
    ]
```

## The selection

For each input, CODE.SECURE@1 runs only those of its 291 rules that the run
rule selects for the input's facts. Bandit runs the selected tests and no
other. Semgrep runs its two rule sets with each rule of the card that the
selection leaves out excluded. A scanner with no selected rule does not run.
[Rule run partitioning](rule-partition.md#the-selection-each-sigil-runs)
states the run rule and the proof.

`dev_harness/sigils/code_secure.py, in _functions_verdict`:

```python
    versions, found = findings(text, root, selection(text, root, CAN_RUN))
```

`dev_harness/sigils/code_secure.py, in findings`, the tests bandit runs and the
rules semgrep runs:

```python
    tests = tuple(rule for rule in BANDIT.rules if f"{BANDIT.tool} {rule}" in to_run)
    rules = [rule for rule in SEMGREP.rules if f"{SEMGREP.tool} {rule}" in to_run]
```

Measured on every tracked Python file of `src/` and every def and class in
them, for each input that tier 2 accepts:

| Input | Inputs | Rules run before | Rules run now, lowest | Median | Highest | Findings with the selection | Findings with every rule |
| ----- | ------ | ---------------- | --------------------- | ------ | ------- | --------------------------- | ------------------------ |
| file | 503 | 291 | 18 | 187 | 202 | 24 | 24 |
| def or class | 13,885 | 291 | 34 | 176 | 198 | 38 | 38 |

## Outputs and flags

| Output | Flag elsewhere | Flag in application source |
| ------ | -------------- | -------------------------- |
| CLEAN | PASS | PASS |
| WEAK | FIX | HOLD |
| REJECTED | BLOCK | BLOCK |

CLEAN means neither tool reports a finding under a rule the card holds. WEAK
carries, for each finding, the tool, its rule id, its CWE id, its severity and
the line. WEAK reads HOLD only when the file the input line names sits in
application source and a finding reaches the severity floor on the card,
medium. A file whose findings are all low reads FIX, and the merge proceeds.

## The command

The input file holds one input per line. Its test pair and sample tree sit in
`harness_fixtures/sigil_code_secure/`. The sample tree holds bandit's own
example files for six tests: B602, B506, B307, B324, B105 and B608.

```
python -m dev_harness.sigils.code_secure <file>
python -m dev_harness.sigils.code_secure --root <folder> <file>
python -m dev_harness.sigils.code_secure --gate <file>
python -m dev_harness.sigils.code_secure --card
```

## Tools and rule sets

The card names two tools and their rule sets, and each finding either tool
reports in the input file under a rule the card holds is an output. One row per
tool, from the card's settings and tier 3. The command prints the versions it
ran.

| Tool | Version on the card | How the card runs it | Rule set |
| ---- | ------------------- | -------------------- | -------- |
| bandit | 1.9.4 | `python -P -m bandit -f json -q -t <tests> -`, with the file's bytes on standard input | the selected tests |
| semgrep | 1.171.0 | `semgrep scan` with `--json --quiet --no-git-ignore` and an `--exclude-rule` for each rule the selection leaves out, in an empty temporary folder that holds a copy of the file under its own name | `p/python` and `p/security-audit` |

## Rules

The card can run the 75 bandit tests and the 216 semgrep rules below. Each test
name comes from `python -m bandit --help`. The last column names each discipline
that houses the test, from the rules.json files under `dev_harness/disciplines/`.

`dev_harness/sigils/code_secure.py, in SETTINGS`: the card prints them as
bandit_rules and semgrep_rules.

| Test | bandit name | Housed by |
| ---- | ----------- | --------- |
| B101 | assert_used | reliability, security |
| B102 | exec_used | security |
| B103 | set_bad_file_permissions | security |
| B104 | hardcoded_bind_all_interfaces | security |
| B105 | hardcoded_password_string | security |
| B106 | hardcoded_password_funcarg | security |
| B107 | hardcoded_password_default | security |
| B108 | hardcoded_tmp_directory | security |
| B110 | try_except_pass | reliability, security |
| B112 | try_except_continue | reliability, security |
| B113 | request_without_timeout | security |
| B201 | flask_debug_true | security |
| B202 | tarfile_unsafe_members | security |
| B301 | pickle | security |
| B302 | marshal | security |
| B303 | md5 | security |
| B304 | ciphers | security |
| B305 | cipher_modes | security |
| B306 | mktemp_q | security |
| B307 | eval | security |
| B308 | mark_safe | security |
| B310 | urllib_urlopen | security |
| B311 | random | security |
| B312 | telnetlib | security |
| B313 | xml_bad_cElementTree | security |
| B314 | xml_bad_ElementTree | security |
| B315 | xml_bad_expatreader | security |
| B316 | xml_bad_expatbuilder | security |
| B317 | xml_bad_sax | security |
| B318 | xml_bad_minidom | security |
| B319 | xml_bad_pulldom | security |
| B321 | ftplib | security |
| B323 | unverified_context | security |
| B324 | hashlib_insecure_functions | security |
| B401 | import_telnetlib | security |
| B402 | import_ftplib | security |
| B403 | import_pickle | security |
| B404 | import_subprocess | security |
| B405 | import_xml_etree | security |
| B406 | import_xml_sax | security |
| B407 | import_xml_expat | security |
| B408 | import_xml_minidom | security |
| B409 | import_xml_pulldom | security |
| B411 | import_xmlrpclib | security |
| B412 | import_httpoxy | security |
| B413 | import_pycrypto | security |
| B415 | import_pyghmi | security |
| B501 | request_with_no_cert_validation | security |
| B502 | ssl_with_bad_version | security |
| B503 | ssl_with_bad_defaults | security |
| B504 | ssl_with_no_version | security |
| B505 | weak_cryptographic_key | security |
| B506 | yaml_load | security |
| B507 | ssh_no_host_key_verification | security |
| B508 | snmp_insecure_version | security |
| B509 | snmp_weak_cryptography | security |
| B601 | paramiko_calls | security |
| B602 | subprocess_popen_with_shell_equals_true | security |
| B603 | subprocess_without_shell_equals_true | security |
| B604 | any_other_function_with_shell_equals_true | security |
| B605 | start_process_with_a_shell | security |
| B606 | start_process_with_no_shell | security |
| B607 | start_process_with_partial_path | security |
| B608 | hardcoded_sql_expressions | security |
| B609 | linux_commands_wildcard_injection | security |
| B610 | django_extra_used | security |
| B611 | django_rawsql_used | security |
| B612 | logging_config_insecure_listen | security |
| B613 | trojansource | security |
| B614 | pytorch_load | security |
| B615 | huggingface_unsafe_download | security |
| B701 | jinja2_autoescape_false | security |
| B702 | use_of_mako_templates | security |
| B703 | django_mark_safe | security |
| B704 | markupsafe_markup_xss | security |

Security houses each semgrep rule below. Reliability also houses three of them:
the Django and Flask nan-injection rules, and the Flask tainted-sql-string rule.

```
generic.html-templates.security.unquoted-attribute-var.unquoted-attribute-var
generic.html-templates.security.var-in-href.var-in-href
generic.html-templates.security.var-in-script-tag.var-in-script-tag
generic.nginx.security.alias-path-traversal.alias-path-traversal
generic.nginx.security.dynamic-proxy-host.dynamic-proxy-host
generic.nginx.security.dynamic-proxy-scheme.dynamic-proxy-scheme
generic.nginx.security.header-injection.header-injection
generic.nginx.security.header-redefinition.header-redefinition
generic.nginx.security.insecure-redirect.insecure-redirect
generic.nginx.security.insecure-ssl-version.insecure-ssl-version
generic.nginx.security.missing-internal.missing-internal
generic.nginx.security.missing-ssl-version.missing-ssl-version
python.airflow.security.audit.formatted-string-bashoperator.formatted-string-bashoperator
python.aws-lambda.security.dangerous-asyncio-create-exec.dangerous-asyncio-create-exec
python.aws-lambda.security.dangerous-asyncio-exec.dangerous-asyncio-exec
python.aws-lambda.security.dangerous-asyncio-shell.dangerous-asyncio-shell
python.aws-lambda.security.dangerous-spawn-process.dangerous-spawn-process
python.aws-lambda.security.dangerous-subprocess-use.dangerous-subprocess-use
python.aws-lambda.security.dangerous-system-call.dangerous-system-call
python.aws-lambda.security.dynamodb-filter-injection.dynamodb-filter-injection
python.aws-lambda.security.mysql-sqli.mysql-sqli
python.aws-lambda.security.psycopg-sqli.psycopg-sqli
python.aws-lambda.security.pymssql-sqli.pymssql-sqli
python.aws-lambda.security.pymysql-sqli.pymysql-sqli
python.aws-lambda.security.sqlalchemy-sqli.sqlalchemy-sqli
python.aws-lambda.security.tainted-code-exec.tainted-code-exec
python.aws-lambda.security.tainted-html-response.tainted-html-response
python.aws-lambda.security.tainted-html-string.tainted-html-string
python.aws-lambda.security.tainted-pickle-deserialization.tainted-pickle-deserialization
python.aws-lambda.security.tainted-sql-string.tainted-sql-string
python.boto3.security.hardcoded-token.hardcoded-token
python.cryptography.security.empty-aes-key.empty-aes-key
python.cryptography.security.insecure-cipher-algorithms-arc4.insecure-cipher-algorithm-arc4
python.cryptography.security.insecure-cipher-algorithms-blowfish.insecure-cipher-algorithm-blowfish
python.cryptography.security.insecure-cipher-algorithms.insecure-cipher-algorithm-idea
python.cryptography.security.insecure-cipher-mode-ecb.insecure-cipher-mode-ecb
python.cryptography.security.insecure-hash-algorithms-md5.insecure-hash-algorithm-md5
python.cryptography.security.insecure-hash-algorithms.insecure-hash-algorithm-sha1
python.cryptography.security.insufficient-dsa-key-size.insufficient-dsa-key-size
python.cryptography.security.insufficient-ec-key-size.insufficient-ec-key-size
python.cryptography.security.insufficient-rsa-key-size.insufficient-rsa-key-size
python.cryptography.security.mode-without-authentication.crypto-mode-without-authentication
python.distributed.security.require-encryption
python.django.security.audit.avoid-insecure-deserialization.avoid-insecure-deserialization
python.django.security.audit.avoid-mark-safe.avoid-mark-safe
python.django.security.audit.csrf-exempt.no-csrf-exempt
python.django.security.audit.custom-expression-as-sql.custom-expression-as-sql
python.django.security.audit.extends-custom-expression.extends-custom-expression
python.django.security.audit.query-set-extra.avoid-query-set-extra
python.django.security.audit.raw-query.avoid-raw-sql
python.django.security.audit.secure-cookies.django-secure-set-cookie
python.django.security.audit.unvalidated-password.unvalidated-password
python.django.security.audit.xss.context-autoescape-off.context-autoescape-off
python.django.security.audit.xss.global-autoescape-off.global-autoescape-off
python.django.security.audit.xss.template-autoescape-off.template-autoescape-off
python.django.security.audit.xss.template-blocktranslate-no-escape.template-blocktranslate-no-escape
python.django.security.audit.xss.template-translate-as-no-escape.template-translate-as-no-escape
python.django.security.audit.xss.template-var-unescaped-with-safeseq.template-var-unescaped-with-safeseq
python.django.security.django-using-request-post-after-is-valid.django-using-request-post-after-is-valid
python.django.security.hashids-with-django-secret.hashids-with-django-secret
python.django.security.injection.code.globals-misuse-code-execution.globals-misuse-code-execution
python.django.security.injection.code.user-eval-format-string.user-eval-format-string
python.django.security.injection.code.user-eval.user-eval
python.django.security.injection.code.user-exec-format-string.user-exec-format-string
python.django.security.injection.code.user-exec.user-exec
python.django.security.injection.command.command-injection-os-system.command-injection-os-system
python.django.security.injection.command.subprocess-injection.subprocess-injection
python.django.security.injection.csv-writer-injection.csv-writer-injection
python.django.security.injection.email.xss-html-email-body.xss-html-email-body
python.django.security.injection.email.xss-send-mail-html-message.xss-send-mail-html-message
python.django.security.injection.mass-assignment.mass-assignment
python.django.security.injection.open-redirect.open-redirect
python.django.security.injection.path-traversal.path-traversal-file-name.path-traversal-file-name
python.django.security.injection.path-traversal.path-traversal-open.path-traversal-open
python.django.security.injection.raw-html-format.raw-html-format
python.django.security.injection.reflected-data-httpresponse.reflected-data-httpresponse
python.django.security.injection.reflected-data-httpresponsebadrequest.reflected-data-httpresponsebadrequest
python.django.security.injection.request-data-fileresponse.request-data-fileresponse
python.django.security.injection.request-data-write.request-data-write
python.django.security.injection.sql.sql-injection-extra.sql-injection-using-extra-where
python.django.security.injection.sql.sql-injection-rawsql.sql-injection-using-rawsql
python.django.security.injection.sql.sql-injection-using-db-cursor-execute.sql-injection-db-cursor-execute
python.django.security.injection.sql.sql-injection-using-raw.sql-injection-using-raw
python.django.security.injection.ssrf.ssrf-injection-requests.ssrf-injection-requests
python.django.security.injection.ssrf.ssrf-injection-urllib.ssrf-injection-urllib
python.django.security.nan-injection.nan-injection
python.django.security.passwords.password-empty-string.password-empty-string
python.django.security.passwords.use-none-for-password-default.use-none-for-password-default
python.fastapi.security.wildcard-cors.wildcard-cors
python.flask.security.audit.app-run-param-config.avoid_app_run_with_bad_host
python.flask.security.audit.app-run-security-config.avoid_using_app_run_directly
python.flask.security.audit.debug-enabled.debug-enabled
python.flask.security.audit.directly-returned-format-string.directly-returned-format-string
python.flask.security.audit.flask-url-for-external-true.flask-url-for-external-true
python.flask.security.audit.hardcoded-config.avoid_hardcoded_config_DEBUG
python.flask.security.audit.hardcoded-config.avoid_hardcoded_config_ENV
python.flask.security.audit.hardcoded-config.avoid_hardcoded_config_SECRET_KEY
python.flask.security.audit.hardcoded-config.avoid_hardcoded_config_TESTING
python.flask.security.audit.render-template-string.render-template-string
python.flask.security.audit.secure-set-cookie.secure-set-cookie
python.flask.security.audit.wtf-csrf-disabled.flask-wtf-csrf-disabled
python.flask.security.dangerous-template-string.dangerous-template-string
python.flask.security.hashids-with-flask-secret.hashids-with-flask-secret
python.flask.security.injection.csv-writer-injection.csv-writer-injection
python.flask.security.injection.nan-injection.nan-injection
python.flask.security.injection.os-system-injection.os-system-injection
python.flask.security.injection.path-traversal-open.path-traversal-open
python.flask.security.injection.raw-html-concat.raw-html-format
python.flask.security.injection.ssrf-requests.ssrf-requests
python.flask.security.injection.subprocess-injection.subprocess-injection
python.flask.security.injection.tainted-sql-string.tainted-sql-string
python.flask.security.injection.tainted-url-host.tainted-url-host
python.flask.security.injection.user-eval.eval-injection
python.flask.security.injection.user-exec.exec-injection
python.flask.security.insecure-deserialization.insecure-deserialization
python.flask.security.open-redirect.open-redirect
python.flask.security.secure-static-file-serve.avoid_send_file_without_path_sanitization
python.flask.security.unescaped-template-extension.unescaped-template-extension
python.flask.security.unsanitized-input.response-contains-unsanitized-input
python.flask.security.xss.audit.template-autoescape-off.template-autoescape-off
python.flask.security.xss.audit.template-unescaped-with-safe.template-unescaped-with-safe
python.jinja2.security.audit.autoescape-disabled-false.incorrect-autoescape-disabled
python.jinja2.security.audit.missing-autoescape-disabled.missing-autoescape-disabled
python.jwt.security.jwt-hardcode.jwt-python-hardcoded-secret
python.jwt.security.jwt-none-alg.jwt-python-none-alg
python.jwt.security.unverified-jwt-decode.unverified-jwt-decode
python.lang.security.audit.conn_recv.multiprocessing-recv
python.lang.security.audit.dangerous-asyncio-exec-tainted-env-args.dangerous-asyncio-exec-tainted-env-args
python.lang.security.audit.dangerous-asyncio-shell-tainted-env-args.dangerous-asyncio-shell-tainted-env-args
python.lang.security.audit.dangerous-code-run-tainted-env-args.dangerous-interactive-code-run-tainted-env-args
python.lang.security.audit.dangerous-os-exec-tainted-env-args.dangerous-os-exec-tainted-env-args
python.lang.security.audit.dangerous-spawn-process-tainted-env-args.dangerous-spawn-process-tainted-env-args
python.lang.security.audit.dangerous-subinterpreters-run-string-tainted-env-args.dangerous-subinterpreters-run-string-tainted-env-args
python.lang.security.audit.dangerous-subprocess-use-tainted-env-args.dangerous-subprocess-use-tainted-env-args
python.lang.security.audit.dangerous-system-call-tainted-env-args.dangerous-system-call-tainted-env-args
python.lang.security.audit.dangerous-testcapi-run-in-subinterp-tainted-env-args.dangerous-testcapi-run-in-subinterp-tainted-env-args
python.lang.security.audit.dynamic-urllib-use-detected.dynamic-urllib-use-detected
python.lang.security.audit.eval-detected.eval-detected
python.lang.security.audit.exec-detected.exec-detected
python.lang.security.audit.hardcoded-password-default-argument.hardcoded-password-default-argument
python.lang.security.audit.httpsconnection-detected.httpsconnection-detected
python.lang.security.audit.insecure-file-permissions.insecure-file-permissions
python.lang.security.audit.insecure-transport.requests.request-session-http-in-with-context.request-session-http-in-with-context
python.lang.security.audit.insecure-transport.requests.request-session-with-http.request-session-with-http
python.lang.security.audit.insecure-transport.requests.request-with-http.request-with-http
python.lang.security.audit.logging.listeneval.listen-eval
python.lang.security.audit.logging.logger-credential-leak.python-logger-credential-disclosure
python.lang.security.audit.mako-templates-detected.mako-templates-detected
python.lang.security.audit.marshal.marshal-usage
python.lang.security.audit.md5-used-as-password.md5-used-as-password
python.lang.security.audit.network.bind.avoid-bind-to-all-interfaces
python.lang.security.audit.network.disabled-cert-validation.disabled-cert-validation
python.lang.security.audit.network.http-not-https-connection.http-not-https-connection
python.lang.security.audit.paramiko-implicit-trust-host-key.paramiko-implicit-trust-host-key
python.lang.security.audit.paramiko.paramiko-exec-command.paramiko-exec-command
python.lang.security.audit.sha224-hash.sha224-hash
python.lang.security.audit.ssl-wrap-socket-is-deprecated.ssl-wrap-socket-is-deprecated
python.lang.security.audit.subprocess-shell-true.subprocess-shell-true
python.lang.security.audit.system-wildcard-detected.system-wildcard-detected
python.lang.security.audit.telnetlib.telnetlib
python.lang.security.audit.weak-ssl-version.weak-ssl-version
python.lang.security.dangerous-code-run.dangerous-interactive-code-run
python.lang.security.dangerous-os-exec.dangerous-os-exec
python.lang.security.dangerous-spawn-process.dangerous-spawn-process
python.lang.security.dangerous-subinterpreters-run-string.dangerous-subinterpreters-run-string
python.lang.security.dangerous-subprocess-use.dangerous-subprocess-use
python.lang.security.dangerous-system-call.dangerous-system-call
python.lang.security.dangerous-testcapi-run-in-subinterp.dangerous-testcapi-run-in-subinterp
python.lang.security.deserialization.avoid-pyyaml-load.avoid-pyyaml-load
python.lang.security.deserialization.avoid-unsafe-ruamel.avoid-unsafe-ruamel
python.lang.security.deserialization.pickle.avoid-cPickle
python.lang.security.deserialization.pickle.avoid-dill
python.lang.security.deserialization.pickle.avoid-pickle
python.lang.security.deserialization.pickle.avoid-shelve
python.lang.security.insecure-hash-algorithms-md5.insecure-hash-algorithm-md5
python.lang.security.insecure-hash-algorithms.insecure-hash-algorithm-sha1
python.lang.security.insecure-hash-function.insecure-hash-function
python.lang.security.insecure-uuid-version.insecure-uuid-version
python.lang.security.unverified-ssl-context.unverified-ssl-context
python.lang.security.use-defused-xml-parse.use-defused-xml-parse
python.lang.security.use-defused-xml.use-defused-xml
python.lang.security.use-defused-xmlrpc.use-defused-xmlrpc
python.pycryptodome.security.insecure-cipher-algorithm-blowfish.insecure-cipher-algorithm-blowfish
python.pycryptodome.security.insecure-cipher-algorithm-des.insecure-cipher-algorithm-des
python.pycryptodome.security.insecure-cipher-algorithm-rc2.insecure-cipher-algorithm-rc2
python.pycryptodome.security.insecure-cipher-algorithm-rc4.insecure-cipher-algorithm-rc4
python.pycryptodome.security.insecure-cipher-algorithm.insecure-cipher-algorithm-xor
python.pycryptodome.security.insecure-hash-algorithm-md2.insecure-hash-algorithm-md2
python.pycryptodome.security.insecure-hash-algorithm-md4.insecure-hash-algorithm-md4
python.pycryptodome.security.insecure-hash-algorithm-md5.insecure-hash-algorithm-md5
python.pycryptodome.security.insecure-hash-algorithm.insecure-hash-algorithm-sha1
python.pycryptodome.security.insufficient-dsa-key-size.insufficient-dsa-key-size
python.pycryptodome.security.insufficient-rsa-key-size.insufficient-rsa-key-size
python.pycryptodome.security.mode-without-authentication.crypto-mode-without-authentication
python.pymongo.security.mongodb.mongo-client-bad-auth
python.pyramid.audit.authtkt-cookie-httponly-unsafe-default.pyramid-authtkt-cookie-httponly-unsafe-default
python.pyramid.audit.authtkt-cookie-httponly-unsafe-value.pyramid-authtkt-cookie-httponly-unsafe-value
python.pyramid.audit.authtkt-cookie-samesite.pyramid-authtkt-cookie-samesite
python.pyramid.audit.authtkt-cookie-secure-unsafe-default.pyramid-authtkt-cookie-secure-unsafe-default
python.pyramid.audit.authtkt-cookie-secure-unsafe-value.pyramid-authtkt-cookie-secure-unsafe-value
python.pyramid.audit.csrf-origin-check-disabled-globally.pyramid-csrf-origin-check-disabled-globally
python.pyramid.audit.csrf-origin-check-disabled.pyramid-csrf-origin-check-disabled
python.pyramid.audit.set-cookie-httponly-unsafe-default.pyramid-set-cookie-httponly-unsafe-default
python.pyramid.audit.set-cookie-httponly-unsafe-value.pyramid-set-cookie-httponly-unsafe-value
python.pyramid.audit.set-cookie-samesite-unsafe-default.pyramid-set-cookie-samesite-unsafe-default
python.pyramid.audit.set-cookie-samesite-unsafe-value.pyramid-set-cookie-samesite-unsafe-value
python.pyramid.audit.set-cookie-secure-unsafe-default.pyramid-set-cookie-secure-unsafe-default
python.pyramid.audit.set-cookie-secure-unsafe-value.pyramid-set-cookie-secure-unsafe-value
python.pyramid.security.csrf-check-disabled-globally.pyramid-csrf-check-disabled-globally
python.pyramid.security.direct-use-of-response.pyramid-direct-use-of-response
python.pyramid.security.sqlalchemy-sql-injection.pyramid-sqlalchemy-sql-injection
python.requests.security.disabled-cert-validation.disabled-cert-validation
python.requests.security.no-auth-over-http.no-auth-over-http
python.sqlalchemy.security.audit.avoid-sqlalchemy-text.avoid-sqlalchemy-text
python.sqlalchemy.security.sqlalchemy-sql-injection.sqlalchemy-sql-injection
python.twilio.security.twiml-injection.twiml-injection
```

## Rules left off

The card leaves no scope rule off. Its left setting is empty for both tools.
