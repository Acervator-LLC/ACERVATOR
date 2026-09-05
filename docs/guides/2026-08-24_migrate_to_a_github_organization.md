# Move Acervator to a GitHub organization

Written 2026-08-24, at v3.26.0, HEAD `de16ee7`.
Companion tool: `tools/migration_verifier.py`.

Read the first section before you do anything. It holds the one decision
that matters. The rest is a checklist. Work down it in order.

---

## 1. The one decision: Transfer the repository. Do not make a new one.

GitHub gives you two ways to get this code into an organization.

1. **Transfer repository.** Settings, Danger Zone, "Transfer ownership".
2. **Make a new repository in the organization and push to it.**

**Use Transfer. Option 2 destroys work that cannot be rebuilt.**

A new repository starts its issue numbering at 1. Your issues, their
comments, and your collaborator's attribution on his 29 issues do not
come with the code. The git history would arrive; everything around it
would not.

That matters more here than in most projects, because this repository
talks about its own issue numbers constantly:

| Measured 2026-08-24 on `de16ee7` | Count |
|---|---|
| Issue citations in tracked files | 479 |
| Files holding at least one | 125 |
| Distinct issue numbers cited | 50 |
| Of the last 60 commit subjects, how many name an issue | 42 |

Those citations are **prose, not links**. A test docstring says "issue #96
measured that...". An audit says "#102's harness". Nothing breaks if the
numbers stop pointing at the right issues. No test fails. No link 404s.
The sentences keep reading perfectly and start being wrong.

That is the exact failure class this project spent a night eliminating:
**wrong-but-plausible citations**. A fresh repository would create 479 of
them in one action.

Transfer keeps the numbers. Take the ten extra minutes.

---

## 2. What Transfer carries, and what it does not

Every claim below carries its source. **[GitHub docs]** marks a claim that
comes from GitHub's own pages, which section 8 lists. **[measured]** marks a
claim this tool measured on your trees on 2026-08-24. **[inferred]** marks
reasoning on top of the other two. No official page states an
**[inferred]** claim, so each one carries the label as a warning.

### Carried

| Thing | Source |
|---|---|
| Issues, pull requests, wiki, stars, watchers | **[GitHub docs]** |
| Git history and commits, unchanged | **[GitHub docs]** |
| All Git LFS objects | **[GitHub docs]** |
| Webhooks, services, secrets, deploy keys stay associated | **[GitHub docs]** |
| Existing forks stay associated with the repository | **[GitHub docs]** |
| The original owner becomes a collaborator | **[GitHub docs]** |
| Other existing collaborators stay | **[GitHub docs]** |
| Redirects: "All links to the previous repository location are automatically redirected to the new location" | **[GitHub docs]** |
| `git clone`, `git fetch` and `git push` against the old URL redirect to the new one | **[GitHub docs]** |

### Issue numbers: read this carefully

**GitHub's transfer page never says that a transfer keeps issue numbers.**
Be honest about that. The documented facts follow, and then the step from
them.

* The page says issues transfer with the repository, and that all links to
  the old location redirect. **[GitHub docs]**
* The separate page on transferring **one issue** to another repository
  says "The original URL redirects to the new issue's URL". That sentence
  shows a single transferred issue gets a **new number**. **[GitHub docs]**
* The two are different operations. Transferring a repository moves the
  whole issue database with the repository; it does not re-file each issue
  into a different repository's numbering. **[inferred]**

**Conclusion: a repository transfer keeps issue numbers. Transferring
issues one at a time does not.** No GitHub page states the first half. Read
it as a step, not as a quotation. For that reason
`tools/migration_verifier.py` records every issue number and title before
the move, then compares them after. Measure this. Do not trust the step.

### Not carried, or changed

| Thing | Source |
|---|---|
| Issue assignees: moving to an organization, "issues assigned to members in the organization remain intact, and all other issue assignees are cleared" | **[GitHub docs]** |
| Issue types: a transfer between organizations keeps only the types that match. It drops the rest | **[GitHub docs]** |
| GitHub Pages: "We don't redirect GitHub Pages associated with the repository" | **[GitHub docs]** |
| Packages may lose their link to the repository, depending on the registry | **[GitHub docs]** |
| Read-only collaborators are not transferred (organization to personal direction) | **[GitHub docs]** |
| A private repository moved to a **Free** account loses protected branches and Pages | **[GitHub docs]** |
| Project site URLs are not redirected | **[GitHub docs]** |
| Calls to a GitHub **Action** hosted by the repository are not redirected; workflows using it fail with `repository not found` | **[GitHub docs]** |

**The Actions row applies in part.** `.github/workflows/ci.yml` runs on
this repository, so a transfer must be followed by a CI run to confirm the
workflow still triggers. Nothing here **publishes** an Action for another
repository to call, so the `repository not found` failure that row
describes cannot reach anyone else. **[measured]**

### Local clones

Old URLs keep working through redirects. **[GitHub docs]** GitHub still says
"we strongly recommend updating any existing local clones to point to the
new repository URL". **[GitHub docs]**

Follow that recommendation. A redirect hides a stale remote. The push
succeeds, so nothing tells you that the tree still names the old URL. Two
trees then disagree and show no symptom. Section 6 repoints both.

### Before you start: requirements

You must have permission to create a repository in the target
organization, and the organization must not already hold a repository of
that name, or a fork in the same network. **[GitHub docs]**

---

## 3. The pre-push hook was retired. CI is the gate.

**This section described a hook that no longer exists, and its removal was
deliberate.** `.githooks/pre-push` refused to push a commit the release
gate had not stamped. It was removed in `8b7097b` on 2026-08-26:

> remove the pre-push gate hook; CI replaces it
>
> `.github/workflows/ci.yml` runs lint and both test lanes on every push
> and pull request. The local hook only bound a clone that opted in.

`.gate_stamp.json` went with it. `tools/gate.py` still runs the gate on
demand; nothing reads a stamp from it any more. **[measured 2026-09-03]**

`core.hooksPath` is still set to `.githooks` in the primary tree and now
points at a directory that is not there. Git finds no hook and pushes.
That is the intended state, not a fault.

**A transfer does not touch any of this.** `.github/workflows/ci.yml` is
the gate. Confirm after the move that the workflow still triggers on the
new remote; ignore section 6's `core.hooksPath` steps, which predate the
removal.

---

## 4. Before you touch anything

- [ ] **4.1** Land or park in-flight work. Issue #101 was in flight on
      2026-08-24. Do not migrate mid-merge.
- [ ] **4.2** Both trees clean: `git status` shows nothing you care about.
- [ ] **4.3** Get a green gate: `python -m tools.gate`. No stamp file to
      compare it against — the stamp and the pre-push hook that read it
      were retired in `8b7097b`. See section 3.
      **[measured 2026-09-03]**
- [ ] **4.4** Make `gh` REACHABLE, so the baseline can record your
      issues. Without issue data the verifier cannot answer the single
      most important question after the move.

      Reachable is the condition the tool tests. It is wider than
      being on PATH. The verifier asks `shutil.which("gh")` first, and
      then looks in the standard install directories: `%ProgramFiles%`
      and `%ProgramFiles(x86)%\GitHub CLI`, the winget link directory
      `%LOCALAPPDATA%\Microsoft\WinGet\Links`, the chocolatey and
      scoop shim directories, and the usual POSIX `bin` directories.
      An install at `C:\Program Files\GitHub CLI\gh.exe` is found
      even when `gh` is on PATH in no shell. **[measured 2026-08-24:
      that is this machine]**

      Check it, and install only if the check fails:

      ```
      python -c "from tools.migration_verifier import resolve_program; print(resolve_program('gh'))"
      ```

      `None` means the tool cannot reach `gh` anywhere. Then install
      it, or use the export in 4.5:

      ```
      winget install --id GitHub.cli
      gh auth login
      ```

      A path means the tool WILL use it. You still need to run
      `gh auth login` once, because a `gh` that cannot authenticate
      reads no issues.

- [ ] **4.5** **Capture the baseline. Do this BEFORE the transfer.**

      ```
      cd <your working tree>
      python -m tools.migration_verifier capture --out ..\migration_baseline.json
      ```

      Read the last line. If it says `issues NOT CAPTURED`, stop and fix
      4.4. A baseline without issue data proves nothing about your issues.
      The reason on that line names where the tool looked.

      If you cannot reach `gh`, export the issues by hand from any
      machine that has it and pass the file:

      ```
      # both files are written by these commands and are not in the tree
      gh issue list --repo ekthelius/ACERVATOR---THE-ACCUMULATION-TRADING-PLATFORM \
          --state all --limit 1000 --json number,title,state > issues.json
      python -m tools.migration_verifier --issues-json issues.json capture --out ..\migration_baseline.json
      ```

      A PowerShell 5.1 `Out-File -Encoding utf8` writes a BOM. The
      reader opens the export as `utf-8-sig`, so a file with a BOM and
      a file without one both read. **[measured 2026-08-24: both give
      `CAPTURE_EXIT=0`]**

- [ ] **4.6** **Put the baseline somewhere outside both repositories.** The
      file holds your only record of correct. `..\` already sits outside.
      Keep it there and never commit it.
- [ ] **4.7** Write down the old URL:
      `https://github.com/ekthelius/ACERVATOR---THE-ACCUMULATION-TRADING-PLATFORM.git`
      **[measured]**

---

## 5. Do the transfer

- [ ] **5.1** Create the organization on GitHub, if it does not exist.
- [ ] **5.2** Confirm you can create repositories in it.
- [ ] **5.3** In the repository: **Settings**, scroll to **Danger Zone**,
      **Transfer ownership**.
- [ ] **5.4** Enter the organization as the new owner. Confirm.
- [ ] **5.5** Wait for GitHub to finish. Load the new URL in a browser.
- [ ] **5.6** Open three or four issues you remember by number. Confirm
      that each keeps its number and its comments. Section 7 measures this
      properly. Treat 5.6 as the eyeball check.

Write the new URL here as you go:

```
NEW URL: https://github.com/____________________/____________________.git
```

---

## 6. Repoint both trees, and restore both hooks

**Run all four commands. Two trees, two things each.** One skipped command
is the failure mode. The redirect hides a stale remote, and a missing hook
reports nothing.

- [ ] **6.1** Primary tree, remote:

      ```
      git -C <your working tree> remote set-url origin NEW_URL
      ```

- [ ] **6.2** Desktop tree, remote:

      ```
      git -C <your second working tree> remote set-url origin NEW_URL
      ```

- [ ] **6.3** Primary tree, hook:

      ```
      git -C <your working tree> config core.hooksPath .githooks
      ```

- [ ] **6.4** Desktop tree, hook. **This tree has no value today. You are
      setting it for the first time, not resetting it.**

      ```
      git -C <your second working tree> config core.hooksPath .githooks
      ```

- [ ] **6.5** Update the three tracked files that hardcode the old URL.
      **[measured]**

      | File | Line | Note |
      |---|---|---|
      | `README.md` | 107 | the clone URL |
      | `ACERVATOR_HOP7.md` | 282 | prose |
      | `docs-archive/llm-session-history/DEVELOPMENT_CHRONICLE.md` | 18587 | a **different** repository (SADP). Leave it alone. |

---

## 7. Verify. Do not hope.

```
cd <your working tree>
python -m tools.migration_verifier verify --baseline ..\migration_baseline.json --expect-remote NEW_URL
```

The tool prints one line per check, then a verdict. It only reads. It never
pushes, never edits a remote, and never calls a GitHub mutation.

Exit codes:

| Code | Meaning |
|---|---|
| `0` | GREEN. Every fact survived. |
| `1` | RED. Something named on screen is wrong. |
| `2` | Refused. The baseline file is missing or unreadable. |
| `3` | Not green. Nothing failed, but some checks could not run. |

**Exit 3 is not a pass.** Some check did not run. A `gh` the tool
cannot reach causes this most often. A check that did not run is not a
check that passed. Fix the cause, then run it again.

What it checks:

| Check | Goes RED when |
|---|---|
| `hooks_path_primary` / `hooks_path_desktop` | `core.hooksPath` is unset, or points where no `pre-push` lives. Both go RED now by design: the hook was retired in `8b7097b` |
| `remote_primary` / `remote_desktop` | a tree still carries the old URL, or not the expected one |
| `remotes_agree_between_trees` | the two trees point at different repositories |
| `gate_stamp_binds_head` | the stamp names a commit other than HEAD. Reports UNKNOWN now: `.gate_stamp.json` went with the hook |
| `history_preserved` | the tree no longer holds the commit recorded at capture, so somebody rewrote history |
| `tracked_files` | the tracked file count moved |
| `issue_numbers_preserved` | the repository lost an issue that existed at capture |
| `issue_titles_preserved` | a title changed |
| `issue_open_closed_counts` | the open or closed count moved |
| `reference_set_preserved` | the tree stopped citing a number it used to cite |
| `issue_numbers_still_resolve` | prose cites an issue that existed at capture, and the repository no longer holds it |
| `branch_protection` | never RED. Informational; see section 9. |

If you want the raw data, add `--json`.

---

## 8. Sources

GitHub's own documentation, fetched 2026-08-24:

1. **Transferring a repository** —
   `https://docs.github.com/en/repositories/creating-and-managing-repositories/transferring-a-repository`
   Source for everything in section 2 except the rows named below.
2. **Renaming a repository** —
   `https://docs.github.com/en/repositories/creating-and-managing-repositories/renaming-a-repository`
   Source for the redirect wording, the project-site-URL exception, and the
   GitHub Actions warning.
3. **Transferring an issue to another repository** —
   `https://docs.github.com/en/issues/tracking-your-work-with-issues/administering-issues/transferring-an-issue-to-another-repository`
   Source for "The original URL redirects to the new issue's URL", which is
   what proves single-issue transfer renumbers and repository transfer is a
   different operation.

Every **[measured]** claim came from your two working trees on 2026-08-24
at `de16ee7`. Every **[inferred]** claim reasons on top of sources 1 and 3,
and carries its label at the point of use.

---

## 9. Branch protection: worth re-probing, once

On 2026-08-13 the branch-protection API refused, with
`403 — "Upgrade to GitHub Pro or make this repository public."`

That is a plan limit on a private repository under a personal account.
**An organization may lift it.** Organization plans differ from personal
ones, so the answer can change purely because the owner changed.

Section 3 makes this worth thirty seconds. Today **one local hook, in local
config, that does not travel and reports nothing** carries the green-gate
rule alone. Branch protection would carry the same rule **server-side**. No
clone could drop it. No fresh checkout could miss it.

The verifier re-probes it and reports. It never marks it RED, because this
is an opportunity, not an obligation. To check by hand:

```
gh api repos/ORG/REPO/branches/main/protection
```

If it answers instead of refusing, set up a rule requiring a green gate,
and the hook stops being the only guard.

---

## 10. After

- [ ] **10.1** Push a trivial commit from the **primary** tree. Confirm it
      reaches the new URL and that `.github/workflows/ci.yml` triggers.
      No pre-push hook prints anything; it was retired. See section 3.
- [ ] **10.2** Push from the second tree, if you have one. Same check.
- [ ] **10.3** Re-run the verifier. Expect exit 0.
- [ ] **10.4** Keep `..\migration_baseline.json`. It holds the only record of
      correct. You will want it if something looks wrong in a month.
