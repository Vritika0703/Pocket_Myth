"""Man-Beater Score: who creates separation against MAN coverage, beyond what's expected.

Separation over expected (SOE) = actual separation at the throw minus the separation a typical
player at the same position gets, in the same coverage type, with the same time to throw.
Man-Beater Score = a player's average SOE on routes run against man coverage.

Outputs: output/man_beater_scores.csv, output/man_beater_leaderboard.png,
         output/separation_payoff.png
"""
import os

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

ROOT = os.path.join(os.path.dirname(__file__), "..")
OUT = os.path.join(ROOT, "output")
MIN_MAN_ROUTES = 40

df = pd.read_csv(f"{OUT}/route_separation.csv")

# --- Expected separation: linear model per (position, coverage) on time to throw ---
df["exp_sep"] = np.nan
for (pos, cov), g in df.groupby(["pos", "coverage"]):
    slope, intercept = np.polyfit(g["time_to_throw"], g["sep_at_throw"], 1)
    df.loc[g.index, "exp_sep"] = intercept + slope * g["time_to_throw"]
df["soe"] = df["sep_at_throw"] - df["exp_sep"]


def summarize(g):
    return pd.Series({
        "routes": len(g),
        "sep": g["sep_at_throw"].mean(),
        "soe": g["soe"].mean(),
        "soe_se": g["soe"].std(ddof=1) / np.sqrt(len(g)),
        "target_rate": g["targeted"].mean(),
    })


by = (df.groupby(["nflId", "displayName", "pos", "coverage"]).apply(summarize, include_groups=False)
      .unstack("coverage"))
by.columns = [f"{a}_{b.lower()}" for a, b in by.columns]
by = by.reset_index()
by = by[by["routes_man"] >= MIN_MAN_ROUTES].copy()
by["man_beater"] = by["soe_man"]
by["man_minus_zone"] = by["soe_man"] - by["soe_zone"]
by = by.sort_values("man_beater", ascending=False)
by.round(3).to_csv(f"{OUT}/man_beater_scores.csv", index=False)

print(f"qualified players (>= {MIN_MAN_ROUTES} man routes): {len(by)}")
show = ["displayName", "pos", "routes_man", "sep_man", "man_beater", "soe_se_man",
        "target_rate_man", "soe_zone", "man_minus_zone"]
print("\nTOP 15\n", by[show].head(15).round(2).to_string(index=False))
print("\nBOTTOM 5\n", by[show].tail(5).round(2).to_string(index=False))
print("\ncorr(man_beater, soe_zone):", round(by["man_beater"].corr(by["soe_zone"]), 3))
print("corr(man_beater, target_rate_man):", round(by["man_beater"].corr(by["target_rate_man"]), 3))

# split-half reliability: is the score a stable skill, or noise?
rng = np.random.default_rng(0)
man = df[(df["coverage"] == "Man") & df["nflId"].isin(by["nflId"])].copy()
man["half"] = rng.integers(0, 2, len(man))
halves = man.groupby(["nflId", "half"])["soe"].mean().unstack()
print("split-half corr of man SOE:", round(halves[0].corr(halves[1]), 3))

# --- Chart 1: leaderboard ---
COLORS = {"WR": "#2a6fdb", "TE": "#e07b24", "RB": "#2e9e5b"}
top = by.head(15).iloc[::-1]
fig, ax = plt.subplots(figsize=(9, 7))
labels_y = (top["displayName"] + " (" + top["pos"] + ")  " + top["man_beater"].map("{:+.2f}".format)
            + " yd, n=" + top["routes_man"].astype(int).astype(str))
ax.barh(labels_y, top["man_beater"],
        xerr=1.96 * top["soe_se_man"], color=top["pos"].map(COLORS),
        error_kw={"ecolor": "#999", "capsize": 3, "lw": 1})
ax.axvline(0, color="#333", lw=1)
ax.set_xlabel("Separation over expected vs MAN coverage (yards, at the throw)  ±95% CI")
ax.set_title("Man-Beater Score: who gets open against man coverage\n"
             f"2021 Weeks 1–8, WR/TE/RB with ≥{MIN_MAN_ROUTES} routes vs man",
             loc="left", fontsize=13)
handles = [plt.Rectangle((0, 0), 1, 1, color=c) for c in COLORS.values()]
ax.legend(handles, COLORS.keys(), loc="lower right", frameon=False)
ax.spines[["top", "right"]].set_visible(False)
fig.tight_layout()
fig.savefig(f"{OUT}/man_beater_leaderboard.png", dpi=160)

# --- Chart 2: does separation pay off? target & completion by separation, man vs zone ---
bins = [0, 1, 2, 3, 4, 6, 40]
labels = ["<1", "1–2", "2–3", "3–4", "4–6", "6+"]
wr_te = df[df["pos"].isin(["WR", "TE"])].copy()
wr_te["sep_bin"] = pd.cut(wr_te["sep_at_throw"], bins, labels=labels)
tgt = wr_te.groupby(["coverage", "sep_bin"], observed=True)["targeted"].mean().unstack(0)
comp = (wr_te[wr_te["targeted"]].assign(c=lambda d: d["passResult"] == "C")
        .groupby(["coverage", "sep_bin"], observed=True)["c"].mean().unstack(0))
print("\nWR/TE target rate by separation:\n", tgt.round(3).to_string())
print("WR/TE completion % when targeted:\n", comp.round(3).to_string())

fig, axes = plt.subplots(1, 2, figsize=(11, 4.5), sharex=True)
for ax, data, title in [(axes[0], tgt, "Chance the QB throws to him"),
                        (axes[1], comp, "Completion rate when targeted")]:
    for cov, c in [("Man", "#c8102e"), ("Zone", "#7a7a7a")]:
        ax.plot(labels, data[cov] * 100, marker="o", color=c, lw=2.5, label=cov)
    ax.set_title(title, loc="left")
    ax.set_xlabel("Separation from nearest defender at the throw (yards)")
    ax.yaxis.set_major_formatter(lambda v, _: f"{v:.0f}%")
    ax.spines[["top", "right"]].set_visible(False)
    ax.grid(axis="y", alpha=0.3)
axes[0].legend(frameon=False)
fig.suptitle("Why it matters: WR/TE separation at the throw, man vs zone coverage",
             x=0.01, ha="left", fontsize=13)
fig.tight_layout()
fig.savefig(f"{OUT}/separation_payoff.png", dpi=160)
print("\nsaved charts to output/")

# --- Chart 3: Open vs Fed -- does the QB reward separation against man? ---
q = by.copy()
x_mid, y_mid = 0, q["target_rate_man"].median()
fig, ax = plt.subplots(figsize=(10, 7.5))
ax.scatter(q["man_beater"], q["target_rate_man"] * 100, s=q["routes_man"] * 1.5,
           c=q["pos"].map(COLORS), alpha=0.75, edgecolor="white", lw=0.8)
ax.axvline(x_mid, color="#999", lw=1, ls="--")
ax.axhline(y_mid * 100, color="#999", lw=1, ls="--")
# label the extremes of each quadrant; nudge known collisions
NUDGE = {"Tyreek Hill": (-62, -12), "Adam Humphries": (-88, -12), "A.J. Brown": (5, -11), "Henry Ruggs": (5, -10)}
ignored_q = q[(q["man_beater"] > 0.15) & (q["target_rate_man"] < 0.16)]
lab = pd.concat([q.nlargest(3, "man_beater"), q.nsmallest(3, "man_beater"),
                 q.nlargest(5, "target_rate_man"), ignored_q,
                 q[q["displayName"] == "Ja'Marr Chase"]]).drop_duplicates("nflId")
for _, r in lab.iterrows():
    ax.annotate(r["displayName"], (r["man_beater"], r["target_rate_man"] * 100),
                xytext=NUDGE.get(r["displayName"], (5, 4)), textcoords="offset points",
                fontsize=8.5)
xl, yl = ax.get_xlim(), ax.get_ylim()
for x, y, t, ha, va in [(xl[1], yl[1], "OPEN & FED", "right", "top"),
                         (xl[1], yl[0], "OPEN BUT IGNORED\n(feed him more vs man)", "right", "bottom"),
                         (xl[0], yl[1], "COVERED BUT FED\n(QB trusts tight windows)", "left", "top"),
                         (xl[0], yl[0], "COVERED & IGNORED", "left", "bottom")]:
    ax.text(x, y, t, ha=ha, va=va, fontsize=10, fontweight="bold", color="#888")
ax.set_xlabel("Man-Beater Score (separation over expected vs man, yards)")
ax.set_ylabel("Target rate on routes vs man coverage")
ax.yaxis.set_major_formatter(lambda v, _: f"{v:.0f}%")
ax.set_title("Open vs Fed: do QBs reward the receivers who beat man coverage?\n"
             f"Bubble size = routes vs man (≥{MIN_MAN_ROUTES}); dashed lines = 0 and median target rate",
             loc="left", fontsize=12)
ax.legend(handles, COLORS.keys(), loc="center left", frameon=False)
ax.spines[["top", "right"]].set_visible(False)
fig.tight_layout()
fig.savefig(f"{OUT}/open_vs_fed.png", dpi=160)

ignored = q[(q["man_beater"] > 0) & (q["target_rate_man"] < y_mid)]
print(f"\nOPEN BUT IGNORED (score>0, target rate < median {y_mid:.1%}):")
print(ignored[["displayName", "pos", "man_beater", "target_rate_man", "routes_man"]]
      .round(3).to_string(index=False))
