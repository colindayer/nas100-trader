# VAULT CONSOLIDATION PLAN

_Audit + plan only. Nothing moved or deleted. Execution is Phase 1 of [[MIGRATION_PLAN]]._

## 1. What exists

| Path | Contents | Verdict |
|---|---|---|
| `obsidian_vault/` | **empty** (only `.`/`..`) | stub, never populated |
| `vault/` | contains a **nested** `vault/vault/` with all 31 notes | real content, wrong depth |
| repo root `*.md` | `ARCHITECTURE_V2`, `LIVE_SAFETY_AUDIT`, `RUN`, `DATA_BRIDGE`, `CODE_INVENTORY`, this file | reference docs |

## 2. Why both exist (best reconstruction)
- `obsidian_vault/` was created by an **earlier session as a placeholder** and never
  filled — it's a dead stub.
- `vault/` is the **V2 vault** delivered in the last docs pass. It got **nested one level
  deep** (`vault/vault/...`) by a move/git artifact, so the notes are at the wrong path.
- **No content conflict** — `obsidian_vault/` is empty, so nothing overlaps or contradicts.
  The only problems are (a) a dead stub and (b) a nesting bug.

## 3. Duplicate / overlapping / conflicting notes
- **Duplicates:** none (empty stub can't duplicate).
- **Overlap:** the vault's `06 Execution Engine`, `04 Risk Engine`, `07 Deployment`
  notes summarize the same material as root `ARCHITECTURE_V2.md`. This is intentional
  (vault = operating system, ARCHITECTURE_V2 = blueprint) and they cross-link — keep both.
- **Broken links risk:** the nested `vault/vault/` means `[[...]]` wikilinks that assume
  the vault root is `vault/` may not resolve until flattened.

## 4. Recommended canonical location — ONE vault

**Open the REPO ROOT (`nas100_backtest/`) as the Obsidian vault.** Notes live under
`vault/` (flattened, not nested). Rationale:
- Root reference docs (`ARCHITECTURE_V2`, `LIVE_SAFETY_AUDIT`, `RUN`, `CODE_INVENTORY`,
  `MIGRATION_PLAN`) then resolve in `[[basename]]` links alongside the vault notes.
- One vault, one graph, everything cross-links.
- `obsidian_vault/` is retired.

## 5. Consolidation steps (DO NOT RUN YET — this is Phase 1 of migration)

```
# 1. flatten the nested vault
git mv vault/vault/* vault/            # move 31 notes up one level
rmdir vault/vault                       # remove now-empty nested dir
find vault -name .DS_Store -delete      # junk

# 2. retire the empty stub
rmdir obsidian_vault                    # empty -> safe

# 3. add an .obsidian marker (optional) so the root opens cleanly as a vault
#    (Obsidian creates .obsidian/ on first open; no action needed)
```

## 6. Verification (after execution)
```
find vault -name "*.md" | wc -l         # expect 31
test ! -d obsidian_vault && echo "stub removed"
test ! -d vault/vault && echo "un-nested"
grep -rl "\[\[03-Validated-Strategies" vault | head   # links intact
```
Then in Obsidian: open repo root, enable **Dataview** community plugin, open
`vault/00 Dashboard` — the live-book / incidents tables should populate and Mermaid render.

## 7. What NOT to do
- Don't delete `vault/` content — it's the real vault.
- Don't merge the reference `.md` files into `vault/` — they belong at root and
  cross-link by basename.

Related: [[MIGRATION_PLAN]] · [[CODE_INVENTORY]] · vault at `vault/00 Dashboard.md`
