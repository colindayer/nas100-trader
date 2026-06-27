# Setup Guide

Copy `config.example.ini` to `config.ini`, then fill in the sections you need.
`config.ini` is gitignored — never commit it.

```bash
cp config.example.ini config.ini
```

---

## Alpaca (required for paper trading)

1. Sign up at https://alpaca.markets (free paper account, no deposit)
2. Go to **Paper Trading → API Keys → Generate New Key**
3. Copy **Key ID** and **Secret Key** into `config.ini [alpaca]`

```ini
[alpaca]
key    = PKXXXXXXXXXXXXXXXX
secret = xxxxxxxxxxxxxxxxxxxx
base_url = https://paper-api.alpaca.markets
```

Verify:
```bash
python live_trader.py --broker alpaca --session asian --dry-run
```

---

## Alerts (optional but recommended)

### Telegram
1. Message @BotFather on Telegram → `/newbot` → copy the **token**
2. Message your bot once, then run:
   ```
   curl "https://api.telegram.org/bot<TOKEN>/getUpdates"
   ```
   Copy `"id"` from the `chat` object — that's your `chat_id`
3. Fill `config.ini [alerts]`:
   ```ini
   telegram_token = 1234567890:AAXXXXX
   chat_id        = 123456789
   ```

### Email (Gmail)
1. Enable 2FA on your Google account
2. Go to https://myaccount.google.com/apppasswords → generate a password for "Mail"
3. Fill `config.ini [alerts]`:
   ```ini
   smtp_host = smtp.gmail.com
   smtp_port = 587
   smtp_user = your@gmail.com
   smtp_pass = abcd efgh ijkl mnop   # 16-char app password (no spaces in actual file)
   to_email  = your@gmail.com
   ```

---

## cTrader / FTMO

The cTrader Open API uses OAuth2 + WebSocket. Steps:

1. **Register an application** at https://openapi.ctrader.com
   - Log in with your cTrader ID (same as FTMO/IC Markets cTrader login)
   - Create a new app → copy `client_id` and `client_secret`
2. **Get an access token** (OAuth2 authorization_code flow):
   - Redirect URL: `https://localhost` (for local testing)
   - Authorization URL: `https://connect.spotware.com/apps/auth`
   - Exchange code for token at: `https://connect.spotware.com/apps/token`
   - The resulting `access_token` is long-lived (renew if you get 401s)
3. Fill `config.ini [ctrader]`:
   ```ini
   account_id    = 17143495
   client_id     = YOUR_CLIENT_ID
   client_secret = YOUR_CLIENT_SECRET
   access_token  = YOUR_ACCESS_TOKEN
   host          = demo   # 'live' for funded accounts
   ```
4. Test: `python live_trader.py --broker ctrader --session asian --dry-run`

**Note:** The cTrader Open API uses protobuf over WebSocket for order execution.
The current scaffold (`ctrader_broker.py`) uses the REST v2 endpoints for
account/position reads and will raise `NotConfiguredError` on order placement
until the WS integration is added. The REST endpoints are sufficient for read-only
monitoring.

---

## Tradovate / Apex Trader Funding

1. Create an account at https://trader.tradovate.com (DEMO is free)
2. Register an application at https://tradovate.com/developers → get `app_id` + `app_secret`
3. Fill `config.ini [tradovate]`:
   ```ini
   name       = your_username
   password   = your_password
   app_id     = 1234
   app_secret = xxxxxxxxxxxx
   base_url   = https://demo.tradovateapi.com/v1   # change to live URL for funded
   ```
4. Test auth: `python tradovate_broker.py --test`

**Risk scale note:** `risk_scale = 0.5` is set by default because futures prop
accounts (Apex/Topstep) use tight trailing drawdowns (~5% of account). Half-size
keeps the system's ~7% max DD below the breach threshold.

---

## Dukascopy M1 data

Dukascopy provides free historical tick data at https://datafeed.dukascopy.com/datafeed/
for personal/research use. Do not redistribute the raw BI5 files.

```bash
# Download NAS100 M1 data for a single year
python fetch_dukascopy.py --instrument NAS100USD --year 2024

# Download everything 2019-2025
python fetch_dukascopy.py --all
```

Files are saved to `data/` (gitignored) as parquet.

If you see HTTP 503, try:
- Running from a different IP (some regions are geo-blocked)
- Adding a `Referer: https://www.dukascopy.com/` header (already included in the script)
- Waiting a few hours (CDN rate limits typically reset)

---

## Kill-switch

The `[risk]` section controls the daily session kill-switch:

```ini
[risk]
daily_loss_limit    = 0.05   # stop trading if down >5% on the day
session_start_equity = 0     # auto-set at session start; 0 disables the switch
```

To enable: set `session_start_equity` to your current account equity before each
trading day starts, or script it as a pre-session step.

---

## Railway deployment (cron)

Set these environment variables in your Railway project (replaces config.ini on server):
```
ALPACA_KEY    = your_paper_key
ALPACA_SECRET = your_paper_secret
```

Cron schedule:
```
0 7 * * 1-5   →  python live_trader.py --broker alpaca --session asian
30 14 * * 1-5  →  python live_trader.py --broker alpaca --session orb
0 21 * * 1-5   →  python live_trader.py --broker alpaca --session eod
```
