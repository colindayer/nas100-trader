import urllib.request, json, time, pandas as pd, numpy as np
import warnings; warnings.filterwarnings("ignore")
FEE = 0.0004
SYM = "BTCUSDT"
def get(url): return json.loads(urllib.request.urlopen(url, timeout=20).read())
def funding(sym, start):
    out = []
    for _ in range(80):
        d = get(f"https://fapi.binance.com/fapi/v1/fundingRate?symbol={sym}&limit=1000&startTime={start}")
        if not d: break
        out += d; start = d[-1]["fundingTime"] + 1
        if len(d) < 1000: break
        time.sleep(0.1)
    s = pd.DataFrame(out); s["t"] = pd.to_datetime(s["fundingTime"], unit="ms")
    return s.drop_duplicates("t").set_index("t")["fundingRate"].astype(float)
def klines(host, sym, start, fut=False):
    out = []
    for _ in range(120):
        path = "fapi/v1/klines" if fut else "api/v3/klines"
        d = get(f"https://{host}/{path}?symbol={sym}&interval=8h&limit=1000&startTime={start}")
        if not d: break
        out += d; start = d[-1][0] + 1
        if len(d) < 1000: break
        time.sleep(0.1)
    df = pd.DataFrame(out); df["t"] = pd.to_datetime([r[0] for r in out], unit="ms")
    df["c"] = [float(r[4]) for r in out]
    return df.drop_duplicates("t").set_index("t")["c"]
start = int(pd.Timestamp("2019-09-10").timestamp() * 1000)
print("Fetching funding + spot + perp (8h)...")
f = funding(SYM, start)
spot = klines("api.binance.com", SYM, start, fut=False)
perp = klines("fapi.binance.com", SYM, start, fut=True)
df = pd.DataFrame({"f": f, "spot": spot, "perp": perp}).dropna()
df["basis"] = df["spot"].pct_change() - df["perp"].pct_change()
df["net"] = df["f"] + df["basis"] - FEE * df["basis"].abs()
df = df.dropna()
df["net"].iloc[0] -= 2 * FEE; df["net"].iloc[-1] -= 2 * FEE
ann = np.sqrt(1095)
def blk(s, label):
    eq = (1 + s).cumprod(); yrs = len(s) / 1095
    print(f"  {label}: CAGR={eq.iloc[-1]**(1/yrs)-1:+.1%} Sharpe={s.mean()/s.std()*ann:.2f} maxDD={(eq/eq.cummax()-1).min():.1%} worst8h={s.min():.2%}")
n = len(df)
print(f"\nREALISTIC funding carry {SYM} ({n} periods, fees+basis modeled):")
print(f"  funding +{(df['f']>0).mean():.0%} of time, gross funding {df['f'].mean()*1095:+.1%}/yr")
blk(df["net"].iloc[:int(n*0.6)], "IS ")
blk(df["net"].iloc[int(n*0.6):], "OOS")
print(f"  worst 30d-avg funding (bear stress): {df['f'].rolling(90).mean().min()*1095:+.1%}/yr")
