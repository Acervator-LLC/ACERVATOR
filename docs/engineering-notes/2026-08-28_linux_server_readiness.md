# Can the full app run on a Linux server? — issue #156 verification

**Qualified.** Nothing on the product path is Windows-only and every runtime
dependency installs and imports on Ubuntu 24.04 under CPython 3.13, but the
full application cannot start on a plain headless Linux server in its current
form: it needs a display supplied to it, a Python 3.13 the shipped installer
does not obtain, and Chromium libraries the shipped installer does not install
— and no measurement below is a run of the application on Linux, which nobody
has performed.

**Reference.** This document records a verification. It proposes no code and
changes no production file.

- Issue: **#156 — "Verify that the full app can run in its current form on a
  Linux based server with no loss of functionality or stability."**
- Base commit: `34a3336`, branch `current`.
- Measured in a fresh `git worktree`, read-only against the runtime tree.
- Date: 2026-08-28.

---

## THE ANSWER IN FIVE LINES

| Question | Answer | Instrument |
| --- | --- | --- |
| Is the code Windows-only anywhere on the product path? | **No.** 6 platform branches; every one has a Linux arm or a guard | AST + grep, section 8 |
| Do the dependencies exist for Linux? | **Yes.** 12 of 12 core packages install as Linux wheels for CPython 3.13 | CI run `33222940491` |
| Does the test suite pass on Linux? | **Yes.** 9373 passed, 79 skipped, 14 xfailed | CI run `33222940491`, fast lane |
| Does that prove the application runs? | **No.** The fast lane never calls `main()` and never opens a window | section 4 |
| Can the app start with no display? | **Unverified, and the tree assumes it cannot** | section 6 |

---

## 1. Findings

Severity is stated against the operator's target: the full application running
on a Linux cloud server the way it runs on Windows today.

| # | What | Where (file:line) | How measured | Severity |
| --- | --- | --- | --- | --- |
| 1 | `QApplication` is constructed with no platform-plugin selection and no fallback. Nothing in `src/` or `main.py` sets `QT_QPA_PLATFORM`. | `main.py:928` | grep `QT_QPA_PLATFORM` over the whole tree: hits in `.github/workflows/ci.yml:149`, `deploy/kiosk/systemd/acervator.service:47`, `tests/qt_pixel.py:58`, docs — zero in `src/` or `main.py` | **Blocks running** on a server with no display |
| 2 | The shipped service unit hard-codes a display. `DISPLAY=:0`, `WAYLAND_DISPLAY=wayland-0`, `QT_QPA_PLATFORM=xcb`. | `deploy/kiosk/systemd/acervator.service:43,45,47` | file read | **Blocks running** unless a display is supplied |
| 3 | The installer asks apt for unversioned `python3`; the floor is 3.13. Ubuntu 24.04 apt ships 3.12, Debian 12 ships 3.11. | `deploy/kiosk/install.sh:131`, `deploy/kiosk/lib/common.sh:114-115` | file read; floor constants `ACERVATOR_PYTHON_MIN_MAJOR=3`, `_MINOR=13` vs `pyproject.toml` `requires-python = ">=3.13,<3.14"` | **Blocks running** — the installer's own check at `common.sh:123` refuses the interpreter it just installed |
| 4 | The installer's Qt package list carries no Chromium runtime libraries. `libnss3`, `libasound2`, `libxcomposite1`, `libxdamage1`, `libxrandr2`, `libgbm1`, `libcups2` all absent. The History tab embeds Chromium. | `deploy/kiosk/install.sh:130-150` (list), `src/gui/react_history_panel.py:65,278` | grep for each library name over `install.sh`: exit 1, no match; control grep for `libxcb-cursor0` reports `install.sh:146` | **Degrades** — History tab only, see finding 5 |
| 5 | A `QWebEngineView` failure removes the History tab and logs a warning. It does not stop the app. | `src/gui/main_tabs/history_tab.py:63`, `src/gui/history_tab.py:303-305`, `src/gui/react_history_panel.py:65-73` | read of the `try`/`except ImportError` guard and of the caller's `except Exception` | **Degrades** |
| 6 | No Chromium sandbox flag is set anywhere. QtWebEngine as root on Linux requires `--no-sandbox` or user namespaces. | none — absence | grep `no-sandbox\|QTWEBENGINE_DISABLE_SANDBOX\|QTWEBENGINE_CHROMIUM_FLAGS` over the tree: zero hits; the same pattern reports a planted control line | **Degrades** — History tab, only if the app runs as root |
| 7 | The PyInstaller spec has no Linux keyring backend and raises on an unknown platform. Only `windows` and `macos` are defined. | `tools/spec_common.py:202-215` | file read | **Cosmetic for a server** — the service unit runs from source (`acervator.service:23`), never a frozen binary |
| 8 | Trade sounds are a silent no-op off Windows. `play()` has a `win32` arm and no `else`. | `src/core/sound_engine.py:431-436` | file read; consumers at `src/gui/main_window.py:3279,3672` | **Degrades**, silently |
| 9 | `QtMultimedia` import is guarded; `audio_suite` degrades where the module is absent. Its only reference in `src/` is a `None` assignment. | `src/gui/audio_suite.py:37-46`, `src/gui/main_tabs/retired_tabs.py:76` | file read | **Cosmetic** — off the product path |
| 10 | 38 text-IO calls take the locale codec. None of them corrupts a runtime file across platforms — see section 3. | 26 in `src/`, 2 in `tools/`, 1 in `main.py`, 9 in `download_archive.py` | AST scan, section 8, control proved | **Degrades on Windows**, not on Linux |
| 11 | `winreg`, `ctypes.windll` and `msvcrt` are used, each behind a platform branch with a Linux arm. | `src/core/instance_guard.py:189,504-517`; `src/core/usb_auth.py:225-228` | grep + read of every branch | **No effect** — refuted, section 5 |
| 12 | An absolute user-specific path is committed in dev tooling. Outside issue #156; named once, not repaired here. | `tools/migration_verifier.py:107` | grep `C:/Users` over `src tools *.py` | **Cosmetic** — CLAUDE.md rule 2 violation, off the runtime path |

---

## 2. What only a Linux run can settle

Every item below is **UNVERIFIED**. None can be closed from this tree.

| Question | Why measurement here cannot answer it |
| --- | --- |
| Does `main.py` reach a window on a machine with a virtual display? | `main()` is never entered by any test. No instrument in the repo starts the application. |
| Does Qt abort, or degrade, when no display exists? | Qt's plugin-load failure path is in Qt, not in this tree. The tree contains no fallback either way. |
| Does QtWebEngine render the History tab under Xvfb, VNC or `xcb` on a server with no GPU? | CI proves Chromium loads under `offscreen` on the GitHub image. It proves nothing about `xcb`, about a GPU-less host, or about the package set a plain server has. |
| Is a Secret Service daemon present, so `keyring` finds a real backend? | `SecretStorage-3.5.0` and `jeepney-0.9.0` install on Linux (CI run `33222940491`). Whether a daemon answers on D-Bus is a property of the machine. |
| Do 38 bots trade correctly for a full session there? | No load, latency or duration measurement exists for Linux. |
| Is the drawing smooth enough to use over a remote viewer? | Frame timing was never measured on Linux. |
| Does `/etc/machine-id` give the instance guard a strong identity on a cloud image? | `src/core/instance_guard.py:207` reads it. A machine cloned from a disk image carries the image's id — the docstring states this limit. Unmeasured on any cloud provider. |

---

## 3. The encoding question, resolved

Issue #143 counts text-IO sites with no explicit `encoding=`. The relevant
question for #156 is narrower: **does any file written on one platform get read
on the other through a different codec?**

Measured answer: **no.** Every writer that reaches a shared runtime file emits
ASCII bytes, and ASCII decodes identically under cp1252 and UTF-8.

| Runtime file | Writer | `ensure_ascii` | Reader with no `encoding=` | Verdict |
| --- | --- | --- | --- | --- |
| `~/.acervator/bot_state.json` and its backup | `src/core/state_manager.py:202,282` via `atomic_write_json` | `True` (default, `src/core/io_utils.py:110`) | `state_manager.py:535,553` | ASCII on disk — safe |
| `~/.acervator/reservation_state` | `src/trading/capital_reservation.py:261` via `atomic_write_json` | `True` | `capital_reservation.py:274` | ASCII on disk — safe |
| `~/.acervator/settings.json` | `src/core/settings.py:338-339`, `json.dump` | `True` (default) | `settings.py:358` | ASCII on disk — safe |
| `~/.acervator/settings.toml` | `src/core/settings.py:336`, `tomli_w.dump` | n/a — binary handle | read at `settings.py:354` with `"rb"` | bytes both ways — safe |
| `~/.acervator/journal/journal_*.jsonl` | `src/trading/reconciliation.py:216`, `json.dumps` | `True` (default) | `reconciliation.py:226` | ASCII on disk — safe |
| `~/.acervator_logs/trade/*.log` | `src/core/logging_engine.py:150`, `encoding="utf-8"` | `to_json` at `logging_engine.py:118`, `True` | `logging_engine.py:158`, `encoding="utf-8"` | explicit both ways — safe |
| `~/.acervator_logs/console/system.log` | `src/core/logging_engine.py:581-587`, `encoding="utf-8"`, `errors="replace"` | n/a | not read by the app | explicit — safe |

The remaining no-encoding sites are the residual defect issue #143 already
owns. Their direction is the reverse of the one #156 asks about: a
locale-codec read is **correct on Linux** (UTF-8) and **wrong on Windows**
(cp1252). Python also coerces a `C`/`POSIX` locale to UTF-8, so a systemd unit
with no `LANG` still reads UTF-8.

---

## 4. What CI proves, and what it does not

**Run `33222940491`**, 2026-08-29T00:14:37Z, event `pull_request`, branch
`current`, conclusion `success`.
`https://github.com/Acervator-LLC/ACERVATOR/actions/runs/33222940491`

| Fact | Value | Source in the run log |
| --- | --- | --- |
| Runner image | `ubuntu-24.04`, release `20260823.283` | `Set up job` |
| Interpreter | CPython 3.13.15, from `.python-version` | `actions/setup-python@v5` |
| Apt packages CI adds | `libegl1 libgl1 libxkbcommon0 libdbus-1-3` | `.github/workflows/ci.yml:174` |
| Qt platform | `QT_QPA_PLATFORM: offscreen` | `.github/workflows/ci.yml:149` |
| Fast-lane selector | `pytest -n auto -m "not slow and not archetype" -q` | `.github/workflows/ci.yml:187` |
| Result | `9373 passed, 79 skipped, 14 xfailed, 12 warnings in 365.27s` | `Run fast test suite` |
| Lanes | `changes` ok, `lint` ok, `test` ok, `test-full` **skipped**, `ci-gate` ok | `gh run view --json jobs` |

### It proves

- **Every core dependency has a Linux install for CPython 3.13.** Section 5's
  table lists the exact wheels from this run.
- **PySide6 imports and builds widgets on Linux.** The suite constructs Qt
  widgets under `offscreen`.
- **QtWebEngine loads and Chromium renders on Linux.**
  `tests/test_react_history_panel.py` drives a real `QWebEngineView`
  (`:288-290`), loads a document, and reads `innerText` back out of the DOM.
  Its only skip guard is `pytest.importorskip("PySide6")` at `:238` — there is
  **no** guard for a missing or failing QtWebEngine. 57 tests collect from that
  file. Had the import or the page load failed on Ubuntu, they would have
  errored, and the lane reported zero failures.

### It does not prove

- **The application runs.** `main()` is never called. No test opens a window,
  starts the fleet, or connects to Coinbase.
- **Anything about a display.** Every lane sets `QT_QPA_PLATFORM=offscreen`,
  which is the one platform that needs no display server. `xcb` is never
  exercised.
- **Anything about a minimal server.** The four apt packages are what CI
  **adds to** the GitHub `ubuntu-24.04` image, not a complete list. That image
  ships a large library set. `deploy/kiosk/install.sh:130-150` names 15 further
  libraries as required for the `xcb` plugin, `libxcb-cursor0` above all —
  measured evidence that the CI list is not sufficient elsewhere.
- **Anything the full lane covers.** `test-full` was **skipped**: it runs only
  on push to `main` and on manual dispatch (`.github/workflows/ci.yml:195-197`).
  Its selector is the complement, `-m "slow or archetype"`
  (`.github/workflows/ci.yml:238`). The files it holds are the engine-replay
  suites `tests/test_pin_observability.py` and
  `tests/test_fleet_replay_controller.py` (`tests/conftest.py:899-902`) plus
  every file whose name contains `archetype` (`tests/conftest.py:910-911`).
  **The engine-replay suites have no green Ubuntu result in the last twelve
  runs.**

---

## 5. Runtime dependencies and Linux availability

Core `dependencies` from `pyproject.toml`. The wheel column is what CI run
`33222940491` resolved and installed on `ubuntu-24.04` / CPython 3.13.15.

| Package | Declared | Installed on Linux | Imported in `src/`? |
| --- | --- | --- | --- |
| PySide6 | `>=6.6.0` | `PySide6-6.11.2`, `PySide6_Essentials-6.11.2`, `PySide6_Addons-6.11.2`, `shiboken6-6.11.2` manylinux_2_34 | yes, 219 sites |
| ccxt | `>=4.2.0` | `ccxt-4.5.76-py3-none-any` | yes, `src/exchange/ccxt_connector.py:480` |
| cryptography | `>=42.0.0` | `cryptography-50.0.1` manylinux_2_34 | yes, `src/competition/bot_identity.py:34` |
| keyring | `>=25.0.0` | `keyring-25.7.0`, with `SecretStorage-3.5.0` + `jeepney-0.9.0` | yes, `src/core/encryption.py:194` |
| pandas | `>=2.1.0` | `pandas-3.0.5-cp313` manylinux_2_28 | **no import found** in `src/`, `main.py`, `acervator_watchdog.py` |
| numpy | `>=1.26.0` | `numpy-2.5.2-cp313` manylinux_2_28 | yes, `src/gui/screen_recorder.py:566` |
| ta | `>=0.11.0` | `ta-0.11.0` | **no import found** |
| tomli_w | `>=1.0.0` | `tomli_w-1.2.0-py3-none-any` | yes, `src/core/settings.py:39` |
| aiohttp | `>=3.9.0` | `aiohttp-3.14.3-cp313` manylinux_2_28 | yes, `src/stocks/alpaca_connector.py:291` |
| psutil | `>=5.9.0` | `psutil-7.2.2` manylinux_2_28 | yes, `src/simulator/nuclear_fleet_controller.py:197` |
| defusedxml | `>=0.7.1` | `defusedxml-0.7.1-py2.py3-none-any` | yes, `src/gui/crypto_news_ticker.py:56` |
| certifi | `>=2024.2.2` | `certifi-2026.6.17-py3-none-any` | yes, `src/exchange/ccxt_connector.py:569` |

**12 of 12 install on Linux. Zero are Windows-only.**

Optional extras that touch platform surfaces:

| Extra | Package | Linux status | Guard |
| --- | --- | --- | --- |
| `display` | `luma.oled`, `RPLCD`, `smbus2`, `pillow` | Raspberry Pi hardware | `src/core/mini_display.py` — **no importer** in `src/` or `main.py`; dead on the product path |
| `video` | `opencv-python`, `pillow` | Linux wheels exist | `src/gui/screen_recorder.py:62-84` capability probes; **no importer** in `src/` or `main.py` |
| `charts` | `matplotlib` | Linux wheels exist | `src/design_system.py:46`, unguarded, but no module imports `src.design_system` |
| `monitor` | `httpx` | Linux wheels exist | `src/trading/live_monitor.py:297`, unguarded, imported inside `_call` |

**Non-Python executables the product path calls: none.** Every `subprocess`
call in the tree is either off the product path or platform-guarded:

| Executable | Site | Platform | On the product path? | Failure |
| --- | --- | --- | --- | --- |
| `/usr/sbin/ioreg` | `src/core/instance_guard.py:240` | macOS only, absolute path, `shell=False` | yes | silent — `logger.debug`, returns `None`, identity falls to weak |
| `diskutil` | `src/core/usb_auth.py:274,290` | macOS branch | only via the USB widget | silent — `logger.warning`, empty list |
| `lsblk` | `src/core/usb_auth.py:331` | Linux branch | only via the USB widget | silent — bare `except`, defaults substituted |
| `ffmpeg` | `src/gui/screen_recorder.py:73,424,469` | any | **no** — no importer | loud in the log, `None` returned |
| `xdg-open` / `open` | `src/gui/screen_recorder.py:740,742` | Linux / macOS arms exist | **no** | `logger.warning` |
| `git`, `powershell`, `py-spy` | `tools/gate.py:66`, `tools/build_launcher.py`, `acervator_watchdog.py:103` | dev + build tooling | **no** | n/a |

---

## 6. What the GUI needs with no monitor

| Requirement | Measured state |
| --- | --- |
| Qt platform plugin | **Not selected by the app.** `QT_QPA_PLATFORM` is absent from `src/` and `main.py`. `main.py:928` calls `QApplication(sys.argv)` and lets Qt choose — `xcb` on Linux. |
| The tree's own headless answer | **Supply a display, do not run without one.** `deploy/kiosk/install.sh` `--headless` installs `tigervnc-standalone-server` and `tigervnc-common`; the service unit sets `DISPLAY=:0` and `QT_QPA_PLATFORM=xcb`. |
| Graphics acceleration | **Not needed for the widgets.** grep for `QOpenGL`, `QtQuick`, `QQuickWidget`, `QtQml`, `.qml`, `QSGRender` over `src/` and `main.py`: **zero hits**; the same pattern reports a planted `QOpenGLWidget` import. All painting is `QPainter` on Qt Widgets. |
| Qt modules `src/gui` imports | `QtWidgets` 109, `QtCore` 63, `QtGui` 35, `QtWebEngineWidgets` 2, `QtMultimedia` 1 | 
| Guards on those imports | `QtWebEngineWidgets`: guarded at `src/gui/react_history_panel.py:65-73` and `src/gui/tradingview_chart.py:26-35`. `QtMultimedia`: guarded at `src/gui/audio_suite.py:39-46`. `QtWidgets`/`QtCore`/`QtGui`: guarded once, at `main.py:918-926`, which logs and returns 1. |
| X11 libraries the xcb plugin needs | 15 named at `deploy/kiosk/install.sh:135-149`, `libxcb-cursor0` mandatory since Qt 6.5 |
| Chromium libraries the History tab needs | **Named nowhere in the tree.** Finding 4. |
| Screen geometry calls | `main.py:1203`, `src/gui/bot_live_settings.py:638`, `src/gui/simulator_tab/fleet/sim_visuals.py:123` — all `primaryScreen()`, which returns `None` with no screen. Their null-handling was not audited here. |

---

## 7. Line endings

The premise that 182 tracked files sit on disk as CRLF is **stale**.

| Tree | `git ls-files --eol` |
| --- | --- |
| Fresh worktree at `34a3336` | **770 `i/lf w/lf`**, 2 `i/none w/none`, 2 `i/-text w/-text`, **0 CRLF** of 774 tracked |
| The operator's main clone | 768 `i/lf w/lf`, **2 `i/lf w/crlf`** — `tests/test_harness_is_reachable.py`, `tests/test_one_dependency_source.py` |

`.gitattributes` sets `* text=auto eol=lf`. A Linux deployment is a fresh
clone, so it receives LF for every tracked file, including the shell scripts in
`deploy/kiosk/`. The two CRLF files are tests, not shipped code, and are
artefacts of the main clone only.

---

## 8. Instruments, and the control that proves each can fail

A scan that has never been shown to report is not evidence. Each instrument
below was pointed at a known positive.

| # | Instrument | Negative result | Positive control | Control reported |
| --- | --- | --- | --- | --- |
| 1 | AST case-sensitivity scan: `src.*` import names and path-shaped string literals resolved against an exact-case on-disk inventory | 285 files, 209 `src.*` imports, 5 literal paths: **0 mismatches** | scratch tree with `src/gui/History_Tab.py` on disk imported as `src.gui.history_tab`, and a literal `src/gui/web/History_Panel.css` against a stored `history_panel.css` | **2 findings**, one of each rule |
| 2 | AST text-IO scan: calls to `open`/`read_text`/`write_text`, binary modes and `encoding=` keyword excluded | 38 sites across `src` + `tools` + root | scratch module with 5 calls: 2 lacking `encoding=`, 1 with it, 1 binary, 1 `read_text(encoding=…)` | **2 of 5 reported**, exactly the two intended |
| 3 | grep `QOpenGL\|QtQuick\|QQuickWidget\|QtQml\|\.qml\b\|QSGRender` | 0 hits in `src/` and `main.py` | scratch file with `from PySide6.QtOpenGLWidgets import QOpenGLWidget` | **1 hit** |
| 4 | grep `no-sandbox\|QTWEBENGINE_DISABLE_SANDBOX\|QTWEBENGINE_CHROMIUM_FLAGS\|disable-gpu` | 0 hits tree-wide | scratch file with `QTWEBENGINE_CHROMIUM_FLAGS=--no-sandbox` | **1 hit** |
| 5 | grep for Chromium libraries over `deploy/kiosk/install.sh` | exit 1, 0 hits | same file, pattern `libxcb-cursor0` | **`install.sh:146`** |
| 6 | grep `\bwin32\|winreg\|ctypes\.windll\|windll\|os\.startfile\|msvcrt\|winsound` | 11 hits | the hits are the control — each was read and classified | n/a |
| 7 | grep `sys\.platform\|os\.name\|platform\.system\(\)` | 20 hits | as above | n/a |
| 8 | grep `subprocess\.(run\|Popen\|call\|check_output\|check_call)\|os\.system\|shutil\.which` | 30 hits | as above | n/a |
| 9 | `git ls-files --eol` | 0 CRLF in the worktree | same command on the main clone | **2 CRLF** |
| 10 | `gh run view --log` | — | the log carries `9373 passed` and the wheel filenames quoted above | n/a |

---

## 9. Claims tested and refuted

Each was treated as a probable blocker, then read at the cited line.

| Claim tested | Verdict | Evidence |
| --- | --- | --- |
| `logging_engine.py` uses `os.remove` + `os.rename` for Windows log rotation, which is unsafe on Linux | **Refuted.** It uses `Path.replace` at `src/core/logging_engine.py:189,192,313`. `os.rename`/`os.remove` appear nowhere in `src/` — the only `os.replace` in `src/` is `src/core/io_utils.py:75`. The module docstring at `:235-243` records the deliberate move OFF `remove`+`rename` because it leaves a window in which no backup exists. | grep `os\.(replace\|rename\|remove\|unlink)\(` over `src` |
| A state file written on Windows in cp1252 corrupts when read on Linux | **Refuted.** Every runtime writer emits ASCII. Section 3. | `ensure_ascii` default at `src/core/io_utils.py:110`; grep for `ensure_ascii=False` finds no call site that passes it |
| 182 tracked files are CRLF and will break shell scripts on Linux | **Refuted.** 0 CRLF in a fresh checkout; 2 in the main clone, both tests. Section 7. | `git ls-files --eol` |
| `winreg` and `ctypes.windll` make the app Windows-only | **Refuted.** `src/core/instance_guard.py:261-269` dispatches to `_machine_id_linux` (`:207`, reads `/etc/machine-id`); `:504-517` selects `fcntl.flock` when `os.name != "nt"`. `src/core/usb_auth.py:196-208` dispatches to `_list_usb_linux` (`:315`, reads `/proc/mounts`). | read of every branch |
| `os.startfile` at `src/gui/screen_recorder.py:738` breaks on Linux | **Refuted twice.** It has an `xdg-open` arm at `:742`, and `screen_recorder` has no importer in `src/` or `main.py`. | grep for importers |
| The service unit's `ExecStart` names an entry point under an installed `src` directory, and the repository holds no such module | **Refuted.** `deploy/kiosk/install.sh:289` copies the repository root into `${INSTALL_DIR}/src`, so the unit's `ExecStart` resolves to the root `main.py`. Recorded earlier at `docs/guides/2026-08-23_run_acervator_in_the_cloud.md:164-180`; re-verified here. | read of the `acervator_sync_source` call site |
| A missing keyring backend blocks boot on a headless server | **Refuted.** `KeyringManager.__init__` catches every exception (`src/core/encryption.py:213-216`) and `main.py:861` constructs it for its probe side effect only. No live path calls `store` or `retrieve`; the only `retrieve` caller is `CredentialVault.retrieve` at `src/core/usb_auth.py:477`, a different class. | grep for `KeyringManager` and `.retrieve(` |
| QtWebEngine cannot work on Linux | **Refuted for the CI image.** `tests/test_react_history_panel.py` drives a real Chromium page with no webengine skip guard, and the lane passed. Section 4. Not refuted for a minimal server — finding 4. | CI run `33222940491` |
| A QtWebEngine failure stops the application | **Refuted.** `src/gui/main_tabs/history_tab.py:63` catches it, logs `History tab unavailable`, and sets `_history_tab = None`. | read of the caller |
| The GUI needs a GPU | **Refuted.** Zero OpenGL/QML in `src/` and `main.py`, control proved. | instrument 3 |

---

## 10. Not determined

- Whether the 79 skips in CI run `33222940491` include anything Linux-relevant.
  The lane runs `-q`, so the log carries no per-test skip reasons, and the run
  cannot be re-driven with `-rs` from here.
- Whether `primaryScreen()` returning `None` is handled at `main.py:1203`,
  `src/gui/bot_live_settings.py:638` and
  `src/gui/simulator_tab/fleet/sim_visuals.py:123`. Those call sites were
  located, not audited.
- The exact library set the GitHub `ubuntu-24.04` image already provides.
  That is a property of the runner image, not of this repository, so the gap
  between it and a plain server is stated as a gap and not as a number.
- Whether `deploy/kiosk/install.sh` completes end to end on any Linux machine.
  `tests/test_os_installer_suite.py` checks the file statically; nothing here
  executed it.
- Whether `pandas` and `ta` are dead declarations or reached by a mechanism no
  AST import walk sees. Both are declared core dependencies with no import
  found in `src/`, `main.py` or `acervator_watchdog.py`.

---

## 11. Related documents

- `docs/guides/2026-08-23_run_acervator_in_the_cloud.md` — a how-to for the
  same target, 911 lines, marked `[TREE]`/`[WEB]`/`[UNKNOWN]` per claim. **Two
  of its statements are now stale:** it records that nothing guards against a
  second copy (`src/core/instance_guard.py` now does, wired at
  `main.py:1159-1167`), and it quotes the Python floor as `>=3.11`
  (`pyproject.toml` now states `>=3.13,<3.14`).
- `deploy/kiosk/HARDWARE_GUIDE.md` — the AcervatorOS target hardware.
