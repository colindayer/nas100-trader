#!/bin/bash
# build_app.sh -- assemble "Trading OS.app" (native macOS bundle).
# No py2app, no deps: the bundle's executable execs python3 on trading_os.py.
# Usage:
#   ./desktop/build_app.sh            # build into desktop/dist/
#   ./desktop/build_app.sh --install  # also copy into /Applications
set -euo pipefail

REPO="$(cd "$(dirname "$0")/.." && pwd)"
DESKTOP="$REPO/desktop"
APP="$DESKTOP/dist/Trading OS.app"
PY="$(command -v python3)"

echo "== building Trading OS.app =="
rm -rf "$APP"
mkdir -p "$APP/Contents/MacOS" "$APP/Contents/Resources"

# stamp the real repo path into settings.json (no hardcoded paths in code)
"$PY" - "$REPO" <<'PYEOF'
import json, sys, pathlib
repo = sys.argv[1]
p = pathlib.Path(repo) / "desktop" / "settings.json"
s = json.loads(p.read_text()) if p.exists() else {}
s["repo_path"] = repo
s["vault_path"] = str(pathlib.Path(repo) / "vault")
p.write_text(json.dumps(s, indent=2))
print("  settings.json -> repo_path", repo)
PYEOF

# Info.plist: LSUIElement=1 -> menu-bar app, no dock icon
cat > "$APP/Contents/Info.plist" <<PLIST
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0"><dict>
  <key>CFBundleName</key><string>Trading OS</string>
  <key>CFBundleDisplayName</key><string>Trading OS</string>
  <key>CFBundleIdentifier</key><string>com.nas100.tradingos</string>
  <key>CFBundleVersion</key><string>1.0</string>
  <key>CFBundleExecutable</key><string>trading-os</string>
  <key>CFBundlePackageType</key><string>APPL</string>
  <key>LSUIElement</key><true/>
  <key>LSMinimumSystemVersion</key><string>12.0</string>
</dict></plist>
PLIST

# launcher executable: point python at trading_os.py in the live repo
cat > "$APP/Contents/MacOS/trading-os" <<LAUNCH
#!/bin/bash
# resolve python from login shell so venv/streamlit are on PATH
exec /bin/zsh -lc 'cd "$REPO/desktop" && exec python3 trading_os.py' >> "$REPO/desktop/launcher.log" 2>&1
LAUNCH
chmod +x "$APP/Contents/MacOS/trading-os"

echo "  built: $APP"
if [[ "${1:-}" == "--install" ]]; then
  cp -R "$APP" "/Applications/"
  echo "  installed: /Applications/Trading OS.app"
fi
echo "== done. Launch: open '$APP'  (or from /Applications after --install) =="
