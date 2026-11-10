"""Pocket_Myth, Part 1 - Man score: who creates separation against MAN coverage, beyond what's expected.

Separation over expected (SOE) = actual separation at the throw minus the separation a typical
player gets from the same ALIGNMENT (outside WR / slot / inline TE / backfield), in the same
coverage type, with the same time to throw.

Man score = a player's average SOE on routes vs man coverage, shrunk toward 0 in proportion
to how noisy it is (empirical Bayes), so small samples don't top the list by luck.

Target rate over expected (TROE) = how often he is targeted vs a typical player in the same
alignment and coverage.

Output: output/man_scores.csv (numbers for the separation payoff and Open-vs-Fed are printed)
"""
import os

import numpy as np
import pandas as pd

ROOT = os.path.join(os.path.dirname(__file__), "..")
OUT = os.path.join(ROOT, "output")
MIN_MAN_ROUTES = 40

df = pd.read_csv(f"{OUT}/route_separation.csv")

# --- Expected separation and expected target rate, per (alignment, coverage) ---
df["exp_sep"] = np.nan
for (al, cov), g in df.groupby(["align", "coverage"]):
    slope, intercept = np.polyfit(g["time_to_throw"], g["sep_at_throw"], 1)
    df.loc[g.index, "exp_sep"] = intercept + slope * g["time_to_throw"]
df["soe"] = df["sep_at_throw"] - df["exp_sep"]
df["exp_tgt"] = df.groupby(["align", "coverage"])["targeted"].transform("mean")
df["troe"] = df["targeted"].astype(float) - df["exp_tgt"]

man = df[df["coverage"] == "Man"]
by = man.groupby(["nflId", "displayName", "pos"]).agg(
    routes_man=("soe", "size"), sep_man=("sep_at_throw", "mean"), soe_raw=("soe", "mean"),
    soe_sd=("soe", "std"), target_rate_man=("targeted", "mean"), troe_man=("troe", "mean")).reset_index()
by["soe_se"] = by["soe_sd"] / np.sqrt(by["routes_man"])
zone = df[df["coverage"] == "Zone"].groupby("nflId")["soe"].mean().rename("soe_zone")
by = by.merge(zone, on="nflId", how="left")
by = by[by["routes_man"] >= MIN_MAN_ROUTES].copy()

# --- Empirical-Bayes shrinkage: true-skill variance tau^2 = var(means) - mean(se^2) ---
tau2 = max(by["soe_raw"].var() - (by["soe_se"] ** 2).mean(), 1e-6)
by["shrink"] = tau2 / (tau2 + by["soe_se"] ** 2)
by["man_score"] = by["shrink"] * by["soe_raw"]
by["man_score_se"] = np.sqrt(by["shrink"]) * by["soe_se"]
by = by.sort_values("man_score", ascending=False)
by.round(3).to_csv(f"{OUT}/man_scores.csv", index=False)

print(f"qualified players (>= {MIN_MAN_ROUTES} man routes): {len(by)}   "
      f"signal sd = {np.sqrt(tau2):.2f} yd, avg shrink = {by['shrink'].mean():.2f}")
show = ["displayName", "pos", "routes_man", "soe_raw", "man_score", "troe_man", "soe_zone"]
print("\nTOP 12\n", by[show].head(12).round(3).to_string(index=False))
print("\nBOTTOM 5\n", by[show].tail(5).round(3).to_string(index=False))

rng = np.random.default_rng(0)
m2 = man[man["nflId"].isin(by["nflId"])].copy()
m2["half"] = rng.integers(0, 2, len(m2))
halves = m2.groupby(["nflId", "half"])["soe"].mean().unstack()
print("split-half reliability of man SOE (alignment-adjusted):", round(halves[0].corr(halves[1]), 3))
print("corr(man_score, TROE vs man):", round(by["man_score"].corr(by["troe_man"]), 3))

# --- Does separation pay off? (numbers only; reported in METHODS.md) ---
bins = [0, 1, 2, 3, 4, 6, 40]
labels = ["<1", "1–2", "2–3", "3–4", "4–6", "6+"]
wt = df[df["pos"].isin(["WR", "TE"])].copy()
wt["sep_bin"] = pd.cut(wt["sep_at_throw"], bins, labels=labels)
tgt = wt.groupby(["coverage", "sep_bin"], observed=True)["targeted"].mean().unstack(0)
thr = wt[wt["targeted"]].copy()
thr["depth"] = np.where(thr["depth_at_throw"] < 10, "Short (<10 yd downfield)", "Deep (10+ yd)")
comp = (thr.assign(c=thr["passResult"] == "C")
        .groupby(["depth", "sep_bin"], observed=True)["c"].agg(["mean", "size"]))
print("\nWR/TE completion % when targeted, by depth:\n", comp["mean"].unstack(0).round(3).to_string())
print("counts:\n", comp["size"].unstack(0).to_string())

# --- Open vs Fed (numbers only) ---
q = by.copy()
ignored = q[(q["man_score"] >= 0.05) & (q["troe_man"] <= -0.03)].nsmallest(5, "troe_man")
fed = q[(q["man_score"] <= -0.10) & (q["troe_man"] >= 0.03)].nlargest(4, "troe_man")
print("\nOPEN BUT IGNORED:\n", ignored[["displayName", "pos", "man_score", "troe_man", "routes_man"]]
      .round(3).to_string(index=False))
print("COVERED BUT FED:\n", fed[["displayName", "pos", "man_score", "troe_man", "routes_man"]]
      .round(3).to_string(index=False))
