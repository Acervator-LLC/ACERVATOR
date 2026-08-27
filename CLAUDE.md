# Acervator — CLAUDE.md

Acervator is an **accumulation trading platform**: a Python / PyQt algorithmic
trading system that harvests volatility via the **Scrum/Fold cycle** (sell the
excess above a dollar target, buy back more on the dip) instead of predicting
price direction. Every completed cycle ends holding more of the asset. **This
software trades real money on real exchanges — correctness is not optional.**

- **Entry point:** `main.py` (PyQt GUI). **Python 3.11+.**
- **Runtime data lives OUTSIDE the repo:** `~/.acervator/` (state, credentials)
  and `~/.acervator_logs/` (all logs), centralized in `src/core/log_paths.py`.
  Nothing under those trees is ever written into, or copied into, this repo.

## Repository map — every folder has exactly ONE role

| Path | Role — and only this |
|------|----------------------|
| `src/core/`        | cross-cutting services: logging, state, settings, event bus, release gate |
| `src/trading/`     | the bot brain — Scrum/Fold engine, TA, risk, reconciliation |
| `src/gui/`         | PyQt UI — tabs, dialogs, widgets |
| `src/exchange/`    | crypto exchange integrations |
| `src/stocks/`      | equities / broker connectors |
| `src/competition/` | Proof-of-Accumulation package |
| `src/utils/`       | small shared helpers |
| `tests/`           | ALL tests **and** their fixtures (`tests/fixtures/`) |
| `tools/`           | dev / build tooling |
| `dev_harness/`     | the review archetypes (issue #84 moved them off the product path) |
| `docs/`            | human-written documentation ONLY — design, ADRs, audits, plans |
| `deploy/kiosk/`    | deployment units — systemd, install scripts (use `__USER__` placeholders) |
| `.github/`         | CI/CD, linting, templates — see [`.github/CLAUDE.md`](.github/CLAUDE.md) |

---

# HARD RULES — no exceptions

## 1. A file lives in the folder whose role it fills. Period.

A file's location MUST accurately represent its role in the application. It is
**forbidden** to place a file in a folder that does not describe what that file
is. Concretely, and non-exhaustively:

- **Tests and test fixtures do NOT belong in `docs/`.** They belong in `tests/`
  (fixtures in `tests/fixtures/`). `docs/` is for human-written documentation
  only — never for test inputs, test outputs, or captured run artifacts.
- **Generated or captured output does NOT belong in `docs/`, `src/`, or `tests/`.**
  It goes to `~/.acervator_logs/` or a gitignored artifacts directory — never
  into a tracked source or docs folder.
- **Documentation does NOT belong in `src/` or `tests/`.**

If a file's correct home is unclear, its role is unclear — resolve the role
first. Never dump a file into the nearest convenient directory.

## 2. Local / user-specific directories are NOT allowed. Use a generic. Period.

Absolute, machine- or user-specific paths are **FORBIDDEN everywhere** in this
repository — source, tests, docs, config, tooling, comments, and anything
committed. **No exceptions.** This includes, without limit:

- `C:\Users\<name>\...`, `/Users/<name>/...`, `/home/<name>/...`
- OneDrive / Desktop / AppData / Temp session paths
- any path naming a specific person, machine, home directory, or drive letter

A portable generic is used instead — always:

- **home-relative:** `Path.home() / ".acervator_logs" / ...` (see `src/core/log_paths.py`)
- **repo-relative:** derive from the repo root, e.g. `Path(__file__).resolve().parents[N] / "docs"`
- **tests:** pytest `tmp_path` / `tempfile` — never the real tree. `tests/conftest.py`
  runs a live-tree guard that fails the run on any write into the runtime tree.
- **deployment templates:** `__USER__` / `__INSTALL_DIR__` placeholders
  (see `deploy/kiosk/systemd/acervator.service`)

Never hardcode a personal path. If you need a
location, **derive it** — from `Path.home()`, the repo root, or a temp dir.
