"""Evaluate the labels and models against the 100 hand-labelled check headlines.

Reference ("gold") = the headlines where both annotators gave the same label; disagreements are reported
separately. For every model: accuracy and macro-F1 on the gold set, the share of direction swaps
(bullish <-> bearish, the costliest error), and the confusion matrix for the main models. The LLM is also
scored without the headline that appears as an example in its prompt.

Usage (from the repository root):
    python -m data_pipeline.news.evaluate_check \
        --ninon data/capesize_news/check_100_ninon_completed_1.xlsx \
        --christella data/capesize_news/check_100_christella_done_1.xlsx
Writes data/capesize_news/check_results.md (no article text, only metrics).
"""
import argparse
from pathlib import Path

import pandas as pd
from sklearn.metrics import accuracy_score, cohen_kappa_score, confusion_matrix, f1_score

from . import config

CLASSES = ["A", "B", "C", "D"]  # bullish, neutral, bearish, not relevant
NAMES = {"A": "bullish", "B": "neutral", "C": "bearish", "D": "not relevant"}
CAPESIZE_MAP = {"bullish": "A", "neutral": "B", "bearish": "C", "not relevant": "D"}
TONE_MAP = {"positive": "A", "neutral": "B", "negative": "C"}  # plain FinBERT has no "not relevant"
PROMPT_EXAMPLE = "Baltic index hits one-week high as capesize rates surge"
LABEL_COL = "label (A/B/C/D)"


def load_sheet(path: Path, who: str) -> pd.DataFrame:
    df = pd.read_excel(path)[["id", "title", LABEL_COL]].rename(columns={LABEL_COL: who})
    df[who] = df[who].astype(str).str.strip().str.upper()
    bad = df[~df[who].isin(CLASSES)]
    if len(bad):
        raise ValueError(f"{path.name}: {len(bad)} rows without a valid A/B/C/D label")
    return df


def md(t: pd.DataFrame) -> str:
    try:
        return t.to_markdown()
    except ImportError:  # 'tabulate' not installed
        return "```\n" + t.to_string() + "\n```"


def model_rows(g: pd.DataFrame, models: dict) -> pd.DataFrame:
    rows = []
    for col, name in models.items():
        directional = g[g["gold"].isin(["A", "C"])]
        swaps = ((directional["gold"] == "A") & (directional[col] == "C")) | \
                ((directional["gold"] == "C") & (directional[col] == "A"))
        rows.append({"model": name, "n": len(g),
                     "accuracy": accuracy_score(g["gold"], g[col]),
                     "macro-F1": f1_score(g["gold"], g[col], labels=CLASSES, average="macro", zero_division=0),
                     "direction swaps": swaps.mean() if len(directional) else float("nan")})
    return pd.DataFrame(rows).set_index("model").round(3)


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--ninon", type=Path, required=True)
    p.add_argument("--christella", type=Path, required=True)
    args = p.parse_args()

    n, c = load_sheet(args.ninon, "ninon"), load_sheet(args.christella, "christella")
    h = n.merge(c[["id", "christella"]], on="id")
    kappa = cohen_kappa_score(h["ninon"], h["christella"])
    agree = (h["ninon"] == h["christella"]).mean()

    ft = pd.read_parquet(config.PROCESSED_DIR / "headlines_finetuned_scores.parquet")
    fb = pd.read_parquet(config.PROCESSED_DIR / "headlines_finbert_baseline.parquet")
    g = h.merge(ft[["id", "llm_label", "ft_head_label", "ft_headlead_label"]], on="id") \
         .merge(fb[["id", "fb_title_label", "fb_lead_label"]], on="id")
    for col in ("llm_label", "ft_head_label", "ft_headlead_label"):
        g[col] = g[col].str.lower().map(CAPESIZE_MAP)
    for col in ("fb_title_label", "fb_lead_label"):
        g[col] = g[col].str.lower().map(TONE_MAP)

    gold = g[g["ninon"] == g["christella"]].assign(gold=lambda d: d["ninon"])
    models = {"fb_lead_label": "Plain FinBERT (headline + lead)", "fb_title_label": "Plain FinBERT (headline)",
              "llm_label": "LLM (Qwen2.5-7B)", "ft_headlead_label": "Fine-tuned FinBERT (headline + lead)",
              "ft_head_label": "Fine-tuned FinBERT (headline)"}
    table = model_rows(gold, models)
    llm_99 = model_rows(gold[gold["title"].str.strip() != PROMPT_EXAMPLE], {"llm_label": "LLM, prompt example removed"})
    table = pd.concat([table, llm_99])

    disagreements = pd.crosstab(h["ninon"].map(NAMES), h["christella"].map(NAMES),
                                rownames=["Ninon"], colnames=["Christella"])
    cms = {name: pd.DataFrame(confusion_matrix(gold["gold"], gold[col], labels=CLASSES),
                              index=[f"gold {NAMES[k]}" for k in CLASSES], columns=[NAMES[k] for k in CLASSES])
           for col, name in [("llm_label", "LLM (Qwen2.5-7B)"), ("ft_headlead_label", "Fine-tuned FinBERT (headline + lead)")]}

    txt = (f"# Hand-check results\n\n{len(h)} headlines labelled independently by both annotators.\n\n"
           f"Agreement: {agree:.0%}, Cohen's kappa {kappa:.2f}. Gold set = {len(gold)} headlines where both agree.\n\n"
           f"## Annotators (all {len(h)} headlines)\n\n{md(disagreements)}\n\n"
           f"## Models vs. gold labels\n\n{md(table)}\n\n"
           "Plain FinBERT measures general tone and has no 'not relevant' class, so it cannot score D headlines.\n\n"
           + "".join(f"## Confusion matrix: {k} (rows = gold, columns = model)\n\n{md(v)}\n\n" for k, v in cms.items()))
    out = config.LOCAL_DIR / "capesize_news" / "check_results.md"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(txt, encoding="utf-8")
    print(txt)
    print(f"Saved {out}")


if __name__ == "__main__":
    main()
