"""Receiver-Line Fit, full version: are LATE-opening receivers wasted behind fast-collapsing lines?

Uses output/fit_scores.csv from fit_score.py. Key measure:
  in-time rate = Fit Score / open rate
               = of the routes where he DOES get open, the share where the pocket is still intact.
This removes "how often he gets open" so we isolate the timing match between receiver and line.

Outputs: output/fit_timing.png, output/fit_best_teams.csv
"""
import os
import sys

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(__file__))
OUT = os.path.join(os.path.dirname(__file__), "..", "output")

f = pd.read_csv(f"{OUT}/fit_scores.csv")
f["in_time"] = f["fit"] / f["open_rate"]
p = f.groupby("player").agg(pos=("pos", "first"), mot=("median_open_t", "first"),
                            open_rate=("open_rate", "first"))
p["grp"] = pd.qcut(p["mot"].rank(method="first"), 3, labels=["Early openers", "Mid", "Late openers"])
f = f.merge(p[["grp"]], left_on="player", right_index=True)

# team order by how long the pocket holds (league-wide in-time rate per team)
team_rank = f.groupby("team")["in_time"].mean().sort_values()
worst5, best5 = team_rank.index[:5], team_rank.index[-5:]

g = f.groupby(["grp", "player"], observed=True)
summ = pd.DataFrame({
    "best_line": f[f["team"].isin(best5)].groupby("player")["in_time"].mean(),
    "worst_line": f[f["team"].isin(worst5)].groupby("player")["in_time"].mean(),
}).join(p)
summ["loss"] = summ["best_line"] - summ["worst_line"]
grp = summ.groupby("grp", observed=True)[["mot", "best_line", "worst_line", "loss"]].mean()
print("best-5 lines:", list(best5), " worst-5 lines:", list(worst5))
print(grp.round(3).to_string())
print("corr(median open time, loss):", round(summ["mot"].corr(summ["loss"]), 3))

# --- best/worst teams per receiver (WR/TE only, sorted latest openers first) ---
rows = []
for player, g2 in f[f["pos"].isin(["WR", "TE"])].groupby("player"):
    g2 = g2.sort_values("in_time", ascending=False)
    rows.append({"player": player, "pos": g2["pos"].iat[0],
                 "median_open_s": g2["median_open_t"].iat[0],
                 "best_3_teams": ", ".join(g2["team"].head(3)),
                 "best_in_time_%": round(100 * g2["in_time"].head(3).mean(), 1),
                 "worst_3_teams": ", ".join(g2["team"].tail(3)),
                 "worst_in_time_%": round(100 * g2["in_time"].tail(3).mean(), 1)})
bt = pd.DataFrame(rows).sort_values("median_open_s", ascending=False)
bt["loss_pts"] = bt["best_in_time_%"] - bt["worst_in_time_%"]
bt.to_csv(f"{OUT}/fit_best_teams.csv", index=False)
print("\n", bt.head(10).to_string(index=False))

# --- Figure: (A) in-time rate vs open time, best vs worst lines; (B) loss by group ---
fig, (a1, a2) = plt.subplots(1, 2, figsize=(14, 5.5), gridspec_kw={"width_ratios": [1.6, 1]})
s = summ.sort_values("mot")
a1.scatter(s["mot"], s["best_line"] * 100, color="#2e9e5b", s=28, label="Behind the 5 best pass-blocking lines")
a1.scatter(s["mot"], s["worst_line"] * 100, color="#c8102e", s=28, label="Behind the 5 worst pass-blocking lines")
for _, r in s.iterrows():
    a1.plot([r["mot"]] * 2, [r["worst_line"] * 100, r["best_line"] * 100], color="#bbb", lw=0.8, zorder=0)
for name in s.sort_values("mot").tail(4).index.tolist() + ["Cooper Kupp"]:
    if name in s.index:
        a1.annotate(name, (s.loc[name, "mot"], s.loc[name, "worst_line"] * 100),
                    xytext=(4, -12), textcoords="offset points", fontsize=8)
a1.set_xlabel("When he usually gets open (median seconds after the snap)")
a1.set_ylabel("Pocket still intact when he gets open")
a1.yaxis.set_major_formatter(lambda v, _: f"{v:.0f}%")
a1.set_title("Later openers lose more behind a weak line", loc="left")
a1.legend(frameon=False, fontsize=9, loc="lower left")
a1.spines[["top", "right"]].set_visible(False)

labels = [str(x) for x in grp.index]
a2.bar(labels, grp["loss"] * 100, color=["#7fb8e6", "#3b8bd4", "#0c447c"])
for i, (v, m) in enumerate(zip(grp["loss"] * 100, grp["mot"])):
    a2.text(i, v + 0.2, f"-{v:.1f} pts\n(open ~{m:.1f}s)", ha="center", fontsize=9)
a2.set_ylabel("Drop in 'pocket intact' rate:\nbest-5 lines → worst-5 lines (points)")
a2.set_title("Cost of a weak line, by receiver type", loc="left")
a2.spines[["top", "right"]].set_visible(False)
a2.set_ylim(0, grp["loss"].max() * 100 * 1.35)
fig.suptitle("Receiver-Line Fit: a late-opening receiver needs a line that holds", x=0.01, ha="left",
             fontsize=13)
fig.tight_layout()
fig.savefig(f"{OUT}/fit_timing.png", dpi=150)
print("saved output/fit_timing.png")
