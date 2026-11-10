"""Man-Beater Score: who creates separation against MAN coverage, beyond what's expected.

Separation over expected (SOE) = actual separation at the throw minus the separation a typical
player gets from the same ALIGNMENT (outside WR / slot / inline TE / backfield), in the same
coverage type, with the same time to throw.

Man-Beater Score = a player's average SOE on routes vs man coverage, shrunk toward 0 in proportion
to how noisy it is (empirical Bayes), so small samples don't top the list by luck.

Target rate over expected (TROE) = how often he is targeted vs a typical player in the same
alignment and coverage.

Outputs: output/man_beater_scores.csv, output/man_beater_leaderboard.png,
         output/separation_payoff.png, output/open_vs_fed.png
"""
import os

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

ROOT = os.path.join(os.path.dirname(__file__), "..")
OUT = os.path.join(ROOT, "output")
MIN_MAN_ROUTES = 40
COLORS = {"WR": "#2a6fdb", "TE": "#e07b24", "RB": "#2e9e5b"}

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
by["man_beater"] = by["shrink"] * by["soe_raw"]
by["man_beater_se"] = np.sqrt(by["shrink"]) * by["soe_se"]
by = by.sort_values("man_beater", ascending=False)
by.round(3).to_csv(f"{OUT}/man_beater_scores.csv", index=False)

print(f"qualified players (>= {MIN_MAN_ROUTES} man routes): {len(by)}   "
      f"signal sd = {np.sqrt(tau2):.2f} yd, avg shrink = {by['shrink'].mean():.2f}")
show = ["displayName", "pos", "routes_man", "soe_raw", "man_beater", "troe_man", "soe_zone"]
print("\nTOP 12\n", by[show].head(12).round(3).to_string(index=False))
print("\nBOTTOM 5\n", by[show].tail(5).round(3).to_string(index=False))

rng = np.random.default_rng(0)
m2 = man[man["nflId"].isin(by["nflId"])].copy()
m2["half"] = rng.integers(0, 2, len(m2))
halves = m2.groupby(["nflId", "half"])["soe"].mean().unstack()
print("split-half reliability of man SOE (alignment-adjusted):", round(halves[0].corr(halves[1]), 3))
print("corr(man_beater, TROE vs man):", round(by["man_beater"].corr(by["troe_man"]), 3))

# --- Chart 1: leaderboard ---
top = by.head(15).iloc[::-1]
fig, ax = plt.subplots(figsize=(9, 7))
labels_y = (top["displayName"] + " (" + top["pos"] + ")  " + top["man_beater"].map("{:+.2f}".format)
            + " yd, n=" + top["routes_man"].astype(int).astype(str))
ax.barh(labels_y, top["man_beater"], xerr=1.96 * top["man_beater_se"], color=top["pos"].map(COLORS),
        error_kw={"ecolor": "#999", "capsize": 3, "lw": 1})
ax.axvline(0, color="#333", lw=1)
ax.set_xlabel("Separation over expected vs man coverage (yards at the throw)\n"
              "shrunk for sample size, ±95% interval")
ax.set_title("Man-Beater Score: who gets open against man coverage\n"
             f"vs players in the same alignment; 2021 Wk 1–8, ≥{MIN_MAN_ROUTES} man routes",
             loc="right", fontsize=12)
handles = [plt.Rectangle((0, 0), 1, 1, color=c) for c in COLORS.values()]
ax.legend(handles, COLORS.keys(), loc="lower right", frameon=False)
ax.spines[["top", "right"]].set_visible(False)
fig.tight_layout()
fig.savefig(f"{OUT}/man_beater_leaderboard.png", dpi=160)

# --- Chart 2: does separation pay off? (target rate by coverage; completion split by throw depth) ---
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

fig, axes = plt.subplots(1, 2, figsize=(11.5, 4.6))
for cov, c in [("Man", "#c8102e"), ("Zone", "#7a7a7a")]:
    axes[0].plot(labels, tgt[cov] * 100, marker="o", color=c, lw=2.5, label=f"{cov} coverage")
axes[0].set_title("Chance the QB throws to him", loc="left")
for dep, c in [("Short (<10 yd downfield)", "#2a6fdb"), ("Deep (10+ yd)", "#0c447c")]:
    s = comp.loc[dep]
    s = s[s["size"] >= 30]
    axes[1].plot(list(s.index), s["mean"] * 100, marker="o", color=c, lw=2.5, label=dep)
axes[1].set_title("Completion rate when targeted (same depth compared)", loc="left")
for ax in axes:
    ax.set_xlabel("Separation from nearest defender at the throw (yards)")
    ax.yaxis.set_major_formatter(lambda v, _: f"{v:.0f}%")
    ax.spines[["top", "right"]].set_visible(False)
    ax.grid(axis="y", alpha=0.3)
    ax.legend(frameon=False)
fig.suptitle("Why it matters: separation at the throw pays off, even comparing throws of the same depth (WR/TE)",
             x=0.01, ha="left", fontsize=12)
fig.tight_layout()
fig.savefig(f"{OUT}/separation_payoff.png", dpi=160)

# --- Chart 3: Open vs Fed (both axes adjusted for alignment) ---
q = by.copy()
fig, ax = plt.subplots(figsize=(10, 7.5))
ax.scatter(q["man_beater"], q["troe_man"] * 100, s=q["routes_man"] * 1.5, c=q["pos"].map(COLORS),
           alpha=0.75, edgecolor="white", lw=0.8)
ax.axvline(0, color="#999", lw=1, ls="--")
ax.axhline(0, color="#999", lw=1, ls="--")
ignored = q[(q["man_beater"] >= 0.05) & (q["troe_man"] <= -0.03)].nsmallest(5, "troe_man")
fed = q[(q["man_beater"] <= -0.10) & (q["troe_man"] >= 0.03)].nlargest(4, "troe_man")
lab = pd.concat([q.nlargest(3, "man_beater"), q.nlargest(3, "troe_man"), ignored, fed]).drop_duplicates("nflId")
for _, r in lab.iterrows():
    ax.annotate(r["displayName"], (r["man_beater"], r["troe_man"] * 100), xytext=(5, 4),
                textcoords="offset points", fontsize=8.5)
xl, yl = ax.get_xlim(), ax.get_ylim()
for x, y, t, ha, va in [(xl[1], yl[1], "OPEN & FED", "right", "top"),
                         (xl[1], yl[0], "OPEN BUT IGNORED\n(feed him more vs man)", "right", "bottom"),
                         (xl[0], yl[1], "COVERED BUT FED\n(QB trusts tight windows)", "left", "top"),
                         (xl[0], yl[0], "COVERED & IGNORED", "left", "bottom")]:
    ax.text(x, y, t, ha=ha, va=va, fontsize=10, fontweight="bold", color="#888")
ax.set_xlabel("Man-Beater Score (separation over expected vs man, yards)")
ax.set_ylabel("Targets over expected vs man\n(vs a typical player in the same alignment, % of routes)")
ax.yaxis.set_major_formatter(lambda v, _: f"{v:+.0f}%")
ax.set_title("Open vs Fed: do QBs reward the receivers who beat man coverage?\n"
             f"Bubble size = routes vs man (≥{MIN_MAN_ROUTES}); both axes compare like-aligned players",
             loc="left", fontsize=12)
ax.legend(handles, COLORS.keys(), loc="center left", frameon=False)
ax.spines[["top", "right"]].set_visible(False)
fig.tight_layout()
fig.savefig(f"{OUT}/open_vs_fed.png", dpi=160)
print("\nOPEN BUT IGNORED:\n", ignored[["displayName", "pos", "man_beater", "troe_man", "routes_man"]]
      .round(3).to_string(index=False))
print("COVERED BUT FED:\n", fed[["displayName", "pos", "man_beater", "troe_man", "routes_man"]]
      .round(3).to_string(index=False))
print("saved charts to output/")
