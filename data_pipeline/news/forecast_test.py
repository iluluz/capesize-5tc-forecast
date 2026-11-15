"""With/without-news forecast test for the text branch (docs/03 §3 M1/M2, §4 evaluation).

The text model learns the ML forecast error (residual r = y_true - yhat_ML) from the daily text features;
final forecast = yhat_ML + r_hat. Chronological splits around the Hormuz closure (T0 = 2026-02-28):
    train      start of text data .. 2026-03-27   (T0 + 1 month; same cutoff as the fine-tuned FinBERT)
    validation 2026-03-28 .. 2026-04-27           (chooses the ridge penalty)
    test       2026-04-28 .. 2026-08-28           (T0 + 2 to 6 months; the event-window test)
    extended   2026-04-28 .. last available date  (reported separately)
Every training set is purged by h trading days before the period it is evaluated on, because a forecast
made at t uses returns up to t + h. (With h = 20 this means training ends about one month before
2026-03-28, so it contains almost no post-closure days: an honest but hard test.)

Compared on the same test days, for h = 5 and h = 20:
    ML only | ML + constant (bias correction, no text) | ML + plain FinBERT | ML + fine-tuned FinBERT | ML + LLM
Metrics: MAE, RMSE, direction hit rate, Diebold-Mariano test vs ML only (HAC, h-1 lags) and a moving-block
bootstrap 90% interval of the MAE change. Placebos (docs/03 §4): (a) text shuffled across days (100 draws),
(b) text shifted by 5 trading days (stale news), (c) text from an unrelated period (circular shift by half the
sample). A real effect should disappear in (a) and (c).

Usage (from the repository root):
    python -m data_pipeline.news.forecast_test --ml data/processed/ml_oos_predictions.parquet        # ml-v1.1
    python -m data_pipeline.news.forecast_test --ml data/processed/ml_oos_predictions_v1.0.parquet   # ml-v1.0
Add --log to append one row per model, horizon and test period to experiments/results.csv.
Writes data/processed/forecast_test_results_<ML version>.md and .csv (metrics only), so the results for
ml-v1.1 and ml-v1.0 are kept side by side.
"""
import argparse
import csv
import subprocess
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd
from scipy import stats
from sklearn.linear_model import Ridge
from sklearn.preprocessing import StandardScaler

from . import config

TRAIN_END, VAL_END = pd.Timestamp("2026-03-27"), pd.Timestamp("2026-04-27")
TEST_END = pd.Timestamp("2026-08-28")
ALPHAS = [0.1, 1, 10, 100, 1000]
SCORINGS = {"fb": "plain FinBERT", "ft": "fine-tuned FinBERT", "llm": "LLM (Qwen2.5-7B)"}
N_SHUFFLES = 100
rng = np.random.default_rng(15071)


def text_columns(feats: pd.DataFrame, s: str) -> pd.DataFrame:
    """Small, pre-chosen feature set per scoring (few features: about 150 training days)."""
    net = feats[f"share_bull_{s}"] - feats[f"share_bear_{s}"]
    return pd.DataFrame({
        "sent_ewm5": feats[f"sent_{s}_ewm5"], "sent_ewm20": feats[f"sent_{s}_ewm20"],
        "sent_chg5": feats[f"sent_{s}_chg5"].fillna(0.0),
        "net_share_ewm5": net.ewm(span=5, adjust=False).mean(),
        "volume_rel20": feats["n_headlines_rel20"].fillna(1.0),
    }, index=feats.index)


def split(df: pd.DataFrame, h: int):
    """Train/validation/test masks with an h-trading-day purge before each boundary."""
    pos = pd.Series(np.arange(len(df)), index=df.index)
    first_val, first_test = pos[df.index > TRAIN_END].min(), pos[df.index > VAL_END].min()
    train = (df.index <= TRAIN_END) & (pos < first_val - h).to_numpy()
    # validation only scores the ridge penalty (never used to fit), so it keeps its full month
    val = (df.index > TRAIN_END) & (df.index <= VAL_END)
    trainval = (df.index <= VAL_END) & (pos < first_test - h).to_numpy()
    test = (df.index > VAL_END) & (df.index <= TEST_END)
    extended = df.index > VAL_END
    return train, val, trainval, test, extended


def fit_predict(X: pd.DataFrame, r: pd.Series, masks) -> tuple[np.ndarray, float]:
    """Choose the ridge penalty on validation, refit on train + validation, predict every day."""
    train, val, trainval, *_ = masks
    best_alpha, best_mae = None, np.inf
    for a in ALPHAS:
        sc = StandardScaler().fit(X[train])
        m = Ridge(alpha=a).fit(sc.transform(X[train]), r[train])
        mae = np.abs(r[val] - m.predict(sc.transform(X[val]))).mean()
        if mae < best_mae:
            best_alpha, best_mae = a, mae
    sc = StandardScaler().fit(X[trainval])
    m = Ridge(alpha=best_alpha).fit(sc.transform(X[trainval]), r[trainval])
    return m.predict(sc.transform(X)), best_alpha


def dm_test(e_base: np.ndarray, e_new: np.ndarray, h: int) -> float:
    """Diebold-Mariano p-value on absolute errors, Newey-West variance with h-1 lags (two-sided)."""
    d = np.abs(e_base) - np.abs(e_new)
    n, dbar = len(d), d.mean()
    dc = d - dbar
    var = dc @ dc / n
    for k in range(1, h):
        if k < n:
            var += 2 * (1 - k / h) * (dc[k:] @ dc[:-k]) / n
    if var <= 0:
        return float("nan")
    return float(2 * (1 - stats.norm.cdf(abs(dbar / np.sqrt(var / n)))))


def block_bootstrap(e_base: np.ndarray, e_new: np.ndarray, h: int, reps: int = 2000) -> tuple[float, float]:
    """90% interval of the relative MAE change, moving blocks of length h."""
    n = len(e_base)
    starts = np.arange(n - h + 1)
    out = []
    for _ in range(reps):
        idx = np.concatenate([np.arange(s, s + h) for s in rng.choice(starts, size=int(np.ceil(n / h)))])[:n]
        out.append(np.abs(e_new[idx]).mean() / np.abs(e_base[idx]).mean() - 1)
    return tuple(np.percentile(out, [5, 95]))


def metrics(y: np.ndarray, base: np.ndarray, new: np.ndarray, h: int, with_tests: bool = True) -> dict:
    e_b, e_n = y - base, y - new
    row = {"MAE": np.abs(e_n).mean(), "RMSE": np.sqrt((e_n ** 2).mean()),
           "Theil U": np.sqrt((e_n ** 2).mean()) / np.sqrt((y ** 2).mean()),  # vs the no-change forecast
           "hit rate": (np.sign(new) == np.sign(y)).mean(),
           "MAE vs ML": np.abs(e_n).mean() / np.abs(e_b).mean() - 1}
    if with_tests:
        row["DM p-value"] = dm_test(e_b, e_n, h) if not np.allclose(e_b, e_n) else float("nan")
        lo, hi = block_bootstrap(e_b, e_n, h)
        row["MAE change 90% CI"] = f"[{lo:+.1%}, {hi:+.1%}]"
    return row


def run_horizon(ml: pd.DataFrame, feats: pd.DataFrame, h: int) -> tuple[pd.DataFrame, pd.DataFrame, dict]:
    df = ml[ml["h"] == h].set_index("date").join(feats, how="inner").sort_index()
    df = df[df["sent_fb_ewm20"].notna()]
    r = df["y_true"] - df["yhat"]
    masks = split(df, h)
    train, val, trainval, test, extended = masks
    y, base = df["y_true"].to_numpy(), df["yhat"].to_numpy()

    preds, alphas = {"ML only": base, "ML + constant (no text)": base + r[trainval].mean()}, {}
    for s, name in SCORINGS.items():
        if f"sent_{s}_ewm5" in df:
            rhat, alphas[name] = fit_predict(text_columns(df, s), r, masks)
            preds[f"ML + {name}"] = base + rhat

    rows = []
    for period, mask in (("test (event window)", test), ("extended test", extended)):
        for model, p in preds.items():
            rows.append({"h": h, "period": period, "model": model, "n days": int(mask.sum()),
                         "test_start": df.index[mask].min().date(), "test_end": df.index[mask].max().date(),
                         "ridge penalty": alphas.get(model.replace("ML + ", ""), ""),
                         **metrics(y[mask], base[mask], p[mask], h, with_tests=model != "ML only")})
    results = pd.DataFrame(rows)

    # placebos on the main text model (fine-tuned FinBERT, or the first scoring available)
    s = "ft" if "sent_ft_ewm5" in df else next(k for k in SCORINGS if f"sent_{k}_ewm5" in df)
    X = text_columns(df, s)
    real = metrics(y[test], base[test], preds[f"ML + {SCORINGS[s]}"][test], h, False)["MAE vs ML"]
    shuffled = []
    for _ in range(N_SHUFFLES):
        Xs = X.iloc[rng.permutation(len(X))].set_index(X.index)
        shuffled.append(metrics(y[test], base[test], base[test] + fit_predict(Xs, r, masks)[0][test], h, False)["MAE vs ML"])
    stale = fit_predict(X.shift(5).bfill(), r, masks)[0]
    unrelated = fit_predict(pd.DataFrame(np.roll(X.to_numpy(), len(X) // 2, axis=0), index=X.index, columns=X.columns), r, masks)[0]
    placebo = pd.DataFrame([
        {"h": h, "text": f"real ({SCORINGS[s]})", "MAE vs ML": real},
        {"h": h, "text": f"(a) shuffled, median of {N_SHUFFLES}", "MAE vs ML": float(np.median(shuffled))},
        {"h": h, "text": "(a) shuffled, share doing at least as well as real", "MAE vs ML": float(np.mean(np.array(shuffled) <= real))},
        {"h": h, "text": "(b) stale: shifted by 5 trading days",
         "MAE vs ML": metrics(y[test], base[test], base[test] + stale[test], h, False)["MAE vs ML"]},
        {"h": h, "text": "(c) unrelated period: circular shift",
         "MAE vs ML": metrics(y[test], base[test], base[test] + unrelated[test], h, False)["MAE vs ML"]},
    ])
    info = {"train days": int(train.sum()), "validation days": int(val.sum()), "test days": int(test.sum()),
            "extended test days": int(extended.sum()), "chosen ridge penalty": alphas}
    return results, placebo, info


RESULTS_COLUMNS = ["run_id", "date_utc", "git_commit", "author", "part", "model", "target", "horizon",
                   "test_start", "test_end", "n_test", "mae", "rmse", "theil_u", "hit_rate", "pinball",
                   "coverage80", "dm_p_vs_ffa", "notes"]


def log_runs(results: pd.DataFrame, placebo: pd.DataFrame, version: str, author: str) -> Path:
    """Append one row per model, horizon and test period to experiments/results.csv (README rule)."""
    path = config.REPO_ROOT / "experiments" / "results.csv"
    with path.open(encoding="utf-8") as f:
        header = next(csv.reader(f))
    if header != RESULTS_COLUMNS:
        raise ValueError(f"Unexpected columns in {path}: {header}")
    try:
        commit = subprocess.run(["git", "rev-parse", "--short", "HEAD"], capture_output=True, text=True,
                                cwd=config.REPO_ROOT, check=True).stdout.strip()
    except Exception:
        commit = "unknown"
    now = datetime.now(timezone.utc)
    rows = []
    for _, r in results.iterrows():
        pl = placebo[placebo["h"] == r["h"]].set_index("text")["MAE vs ML"]
        notes = [f"text branch, ML base {version}", f"period: {r['period']}"]
        if r["model"] != "ML only":
            notes += [f"MAE vs ML {r['MAE vs ML']:+.1%}", f"DM p vs ML {r['DM p-value']:.3f}",
                      f"90% CI of MAE change {r['MAE change 90% CI']}"]
        if r["ridge penalty"] != "":
            notes.append(f"ridge penalty {r['ridge penalty']}")
        if "fine-tuned" in r["model"] and r["period"].startswith("test"):
            notes.append("placebos (MAE vs ML): " + ", ".join(f"{k} {v:+.1%}" for k, v in pl.items() if "share" not in k))
        notes.append("theil_u = RMSE / RMSE of the no-change forecast")
        slug = r["model"].replace("ML + ", "").replace(" ", "-").replace("(", "").replace(")", "").lower()
        rows.append({
            "run_id": f"text-{version}-{slug}-h{r['h']}-{'event' if r['period'].startswith('test') else 'ext'}-{now:%Y%m%d%H%M}",
            "date_utc": now.strftime("%Y-%m-%dT%H:%M:%SZ"), "git_commit": commit, "author": author, "part": "text",
            "model": r["model"] if r["model"] == "ML only" or "constant" in r["model"]
                     else f"{r['model']} (ridge on ML residual)",
            "target": "ln(5TC_t+h / 5TC_t)", "horizon": r["h"], "test_start": r["test_start"],
            "test_end": r["test_end"], "n_test": r["n days"], "mae": round(r["MAE"], 6), "rmse": round(r["RMSE"], 6),
            "theil_u": round(r["Theil U"], 4), "hit_rate": round(r["hit rate"], 4), "pinball": "",
            "coverage80": "", "dm_p_vs_ffa": "", "notes": "; ".join(notes)})
    needs_newline = path.read_bytes()[-1:] not in (b"\n", b"")
    with path.open("a", encoding="utf-8", newline="") as f:
        if needs_newline:
            f.write("\n")
        csv.DictWriter(f, fieldnames=RESULTS_COLUMNS, lineterminator="\n").writerows(rows)
    return path


def md(t: pd.DataFrame) -> str:
    try:
        return t.to_markdown(index=False, floatfmt=".4f")
    except ImportError:
        return "```\n" + t.to_string(index=False) + "\n```"


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--ml", type=Path, default=config.PROCESSED_DIR / "ml_oos_predictions.parquet")
    p.add_argument("--log", action="store_true", help="append the runs to experiments/results.csv")
    p.add_argument("--author", default="Ninon")
    args = p.parse_args()

    ml = pd.read_parquet(args.ml)
    ml["date"] = pd.to_datetime(ml["date"]).dt.normalize()
    if (pd.to_datetime(ml["train_end"]) >= ml["date"]).any():
        raise ValueError("Some ML predictions are not out-of-sample (train_end >= date).")
    feats = pd.read_parquet(config.PROCESSED_DIR / "text_daily_features.parquet")
    feats["date"] = pd.to_datetime(feats["date"]).dt.normalize()
    feats = feats.set_index("date")
    version = ", ".join(sorted(ml["model_version"].astype(str).unique()))

    parts, placebos, infos = [], [], {}
    for h in sorted(ml["h"].unique()):
        res, pl, infos[h] = run_horizon(ml, feats, int(h))
        parts.append(res)
        placebos.append(pl)
    results, placebo = pd.concat(parts), pd.concat(placebos)
    shown = results.drop(columns=["test_start", "test_end", "ridge penalty"])

    txt = (f"# With/without-news forecast test\n\nML predictions: {args.ml.name} ({version}). "
           f"Text model: ridge on 5 daily text features, learning the ML residual.\n\n"
           + "".join(f"- h = {h}: {v}\n" for h, v in infos.items())
           + f"\n## Forecast accuracy (MAE vs ML < 0 means the text helps)\n\n{md(shown)}\n\n"
           f"## Placebo tests on the test window\n\n{md(placebo)}\n\n"
           "With h = 20 the test window has only about 4-5 independent observations per month: read the "
           "DM p-values and intervals with caution.\n")
    tag = version.replace(", ", "_").replace(" ", "")
    out = config.PROCESSED_DIR / f"forecast_test_results_{tag}.md"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(txt, encoding="utf-8")
    results.to_csv(out.with_suffix(".csv"), index=False)
    print(txt)
    print(f"Saved {out} and {out.with_suffix('.csv').name}")
    if args.log:
        print(f"Added {len(results)} rows to {log_runs(results, placebo, version, args.author)}")


if __name__ == "__main__":
    main()
