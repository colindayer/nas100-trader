# HUMAN ACTION REQUIRED

Two credentials gate full autonomy. Everything not depending on them is already built and
running. **Neither blocks trading.**

---

## 1. GitHub token on the VPS — unlocks the entire sync loop

**WHAT:** a fine-grained personal access token with `Contents: read and write` on
`colindayer/nas100-trader`.

**WHY:** the VPS currently cannot send anything out or pull anything in. Every `iwr` you paste
and every `type` you run exists only because of this. It is the single remaining reason you are
the message bus.

**ONE-TIME SETUP** (on the VPS, replace the placeholder):
```powershell
cd C:\Users\Administrator
git config --global user.name "desk-vps"
git config --global user.email "desk@localhost"
git remote set-url origin https://<TOKEN>@github.com/colindayer/nas100-trader.git
```

**VERIFY:**
```powershell
git ls-remote origin HEAD
```

**SECURITY:** the token lives in `.git/config` on the VPS only. It is never committed. Scope it
to this one repository. Revoke at github.com/settings/tokens if the VPS is ever compromised.

**UNLOCKS:** VPS pulls code automatically (no more `iwr`); pushes logs, ledger, reviews and
validation reports automatically (no more `type`); your Mac and Obsidian pull them; the desk
becomes readable from anywhere.

### Blocker inside this repo, which is yours to decide
`.gitignore` line 8 is `data/`. **All evidence lives under `data/`.** Syncing it means either:

- **(a)** un-ignore `data/logs/`, `data/challenge/`, `data/brain/`, `data/telemetry/` only —
  small text files, a few MB/year; or
- **(b)** publish to a separate `evidence/` directory that is tracked.

I recommend **(a)**, scoped to those four paths, leaving parquet/CSV caches ignored.

**Also note:** the repo is **1.26 GiB**, dominated by a tracked 1.2 GB
`quantitative-trading-free-lesson` directory. That is why pushes intermittently 500. Scheduled
pushes will inherit this. Removing it from history would make the desk materially more robust.

---

## 2. Anthropic API key on the VPS — optional LLM analyst

**WHAT:** `ANTHROPIC_API_KEY` as a machine environment variable.

**WHY:** to have the nightly review package analysed automatically and produce
`CIO_DECISION.md` / `PATCH_RECOMMENDATIONS.md` / `NEXT_EXPERIMENT.md`.

**ONE-TIME SETUP:**
```powershell
[Environment]::SetEnvironmentVariable("ANTHROPIC_API_KEY","<KEY>","Machine")
```

**SECURITY:** never committed; `.env` is already gitignored.

**COST:** recurring and yours to approve. **Trading never depends on it** — if the key is
absent the orchestrator writes the review package to `data/review_queue/` and continues.

---

## Status without either credential

Already working, unattended: trading, preflight, reconciliation, time exits, learning,
allocation, nightly review, structured event logs, validation reports.

Still manual: moving code in and evidence out.
