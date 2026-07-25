# DEPLOYMENT

## How this repository is deployed (verified, not assumed)
| method | supported | notes |
|--|--|--|
| Git clone / pull | ❌ | the VPS has no clone |
| ZIP release | ❌ | no artifact published |
| **PowerShell file sync** | ✅ **actual method** | SHA-pinned `iwr` per file |
| Docker / CI | ❌ | none |

## The cache trap (root cause of repeated failures)
`raw.githubusercontent.com` **caches by path and ignores `?v=` query strings.** Cache-busted
downloads silently returned stale files, so several debugging sessions tested code that was never
actually installed.

**Always deploy with a commit-SHA URL — immutable, never stale:**
```
https://raw.githubusercontent.com/colindayer/nas100-trader/<COMMIT_SHA>/<path>
```

## Procedure
On the **source machine** (Mac):
```
py deploy.py --manifest        # regenerate MANIFEST.json (34 tracked files)
py deploy.py --sync-script     # emit the SHA-pinned PowerShell block
```
Paste the emitted block into the **VPS** PowerShell. It ends by running:
```
py deploy.py --verify
py healthcheck.py
```

## Verification
```
py deploy.py --verify            # COMPLETE | INCOMPLETE | MODIFIED
py deploy.py --verify --strict   # treat locally-modified files as failure
```
Compares SHA-256 (16 hex) per file against `MANIFEST.json` and reports **missing** and **modified**
files by name. `INCOMPLETE` means the install is not safe to start.

## Rule
**Never start a runner without `py deploy.py --verify` returning COMPLETE and
`py healthcheck.py` reporting zero critical failures.**
