# Reference Pages

Reference. These pages hold research, history, process and evidence that
support the product manual. The PDF does not print them.

The PDF prints a page only when the part table in
[../manual/README.md](../manual/README.md) lists it. This folder is outside
`docs/manual/`, so the build never reads a page here.

`tools/build_product_manual.py` — `body_flowables` prints each part, then every
listed page whose Part cell names that part

```python
for part in manual.part_list.parts:
    ...
    for row in manual.rows:
        if row.part == part.number:
            out.extend(_file_flowables(row, manual, styles))
```

| Page | Part | Covers | Code |
| ---- | ---- | ------ | ---- |
| [13-live-evidence.md](13-live-evidence.md) | 4 | The readers of the year-to-date venue record, the connectors, and what the exchange tests reach | `src/trading/scrumming/reconciliation.py, in sync_ytd_trade_count` |
| [15-venue-compatibility.md](15-venue-compatibility.md) | 4 | Every API-reachable venue against the classes it serves, how each one names an order's size, and whether a scrum's excess survives that size rule | `src/trading/bot_container.py, in guarded_place_order` |
| [16-sector-exchange-product-tree.md](16-sector-exchange-product-tree.md) | 4 | The three nested levels — the six sectors, the venues each one reaches, and the products a venue serves under it with the size rule each product publishes | `src/gui/main_tabs/asset_class_surface.py, in venues_for_class` |
| [11-hop-protocol-and-rules-registry.md](11-hop-protocol-and-rules-registry.md) | 5 | The handoff file and its drift check, the rules registry, and the two versions of the development protocol | `tools/hop_check.py, in main` |
| [09-updates-and-versioning.md](09-updates-and-versioning.md) | 7 | Version derivation, the six readers, the baked bundle value, the release gate, how dependency updates reach the branch | `src/_version.py, in resolve_version` |
| [17-what-the-build-includes.md](17-what-the-build-includes.md) | 7 | The reading that decides which source modules a build carries, what leaves with a module, the outside packages named outright, and what the reading cannot see | `tools/spec_common.py, in reachable_src_modules` |
| [14-development-chronicle.md](14-development-chronicle.md) | 8 | The three records of the work, the corrections that became the instruments, the audits they produced, and what they cost and missed | `dev_harness/harness/rules/story.py, in is_story` |

The Part column gives the part of
[../manual/04-manual-parts.md](../manual/04-manual-parts.md) that a page
supports. The PDF still prints the title and bullets of Parts 4, 5, 7 and 8, and
no page follows them.
