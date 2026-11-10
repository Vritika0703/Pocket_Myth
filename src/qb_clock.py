"""Is each receiver open before HIS OWN quarterback usually throws?

Uses output/fit_routes.csv and output/fit_pockets.csv from fit_score.py.
  open-by time  = time after the snap by which he has been open on half his routes
                  (Kaplan-Meier; routes cut short by the throw count as unknown after that point)
  QB clock      = his team's median time from snap to the end of the dropback
  open at clock = share of his routes on which he is open by his QB's usual throw time

Outputs: output/open_vs_qb_clock.csv, output/qb_clock.png
"""
import os
import sys

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(__file__))
from fit_score import GRID, MIN_ROUTES, km_survival  # noqa: E402

OUT = os.path.join(os.path.dirname(__file__), "..", "output")
COLORS = {"WR": "#2a6fdb", "TE": "#e07b24"}

routes = pd.read_csv(f"{OUT}/fit_routes.csv")
pockets = pd.read_csv(f"{OUT}/fit_pockets.csv")
qb_clock = pockets.groupby("possessionTeam")["dur"].median()
tgt = pd.read_csv(f"{OUT}/route_separation.csv").groupby("nflId")["targeted"].mean()

counts = routes.groupby("nflId").size()
sel = routes[routes["nflId"].isin(counts[counts >= MIN_ROUTES].index) & routes["officialPosition"].isin(["WR", "TE"])]
rows = []
for pid, g in sel.groupby("nflId"):
    F = 1 - km_survival(g["obs_t"], g["opened"])
    team = g["possessionTeam"].mode().iat[0]
    clock = qb_clock[team]
    rows.append({"player": g["displayName"].iat[0], "pos": g["officialPosition"].iat[0], "team": team,
                 "routes": len(g), "open_by_s": GRID[np.argmax(F >= 0.5)] if F[-1] >= 0.5 else np.nan,
                 "qb_clock_s": clock, "open_at_clock": F[np.argmin(np.abs(GRID - round(clock, 1)))],
                 "target_rate": tgt.get(pid, np.nan)})
d = pd.DataFrame(rows)
d["margin_s"] = d["qb_clock_s"] - d["open_by_s"]       # positive = open before the QB usually throws
d = d.sort_values("margin_s")
d.round(3).to_csv(f"{OUT}/open_vs_qb_clock.csv", index=False)

late = d[(d["margin_s"] <= 0) | d["open_by_s"].isna()]
print(f"WR/TE: {len(d)}  open before QB clock: {(d['margin_s'] > 0).sum()}  "
      f"at/after: {(d['margin_s'] <= 0).sum()}  never open on half by 4 s: {d['open_by_s'].isna().sum()}")
print(f"open at clock: mean {d['open_at_clock'].mean():.2f}, range {d['open_at_clock'].min():.2f}-{d['open_at_clock'].max():.2f}")
print("late group by position:", late["pos"].value_counts().to_dict())
print("corr(open at clock, target rate):", round(d["open_at_clock"].corr(d["target_rate"]), 2),
      "| WR only:", round(d[d.pos == "WR"]["open_at_clock"].corr(d[d.pos == "WR"]["target_rate"]), 2))
print(d[["player", "pos", "team", "open_by_s", "qb_clock_s", "margin_s", "open_at_clock"]].head(12)
      .round(2).to_string(index=False))

# ---------- chart ----------
fig, ax = plt.subplots(figsize=(10, 7))
dd = d.dropna(subset=["open_by_s"]).copy()
dd["xj"] = dd["qb_clock_s"] + np.random.default_rng(1).uniform(-0.03, 0.03, len(dd))
ax.scatter(dd["xj"], dd["open_by_s"], s=dd["routes"] / 3, c=dd["pos"].map(COLORS),
           alpha=0.8, edgecolor="white", lw=0.7)
lo, hi = 1.3, 4.0
ax.fill_between([2.3, 3.4], [2.3, 3.4], hi, color="#c8102e", alpha=0.07)
ax.plot([2.3, 3.4], [2.3, 3.4], color="#c8102e", lw=1.2, ls="--")
ax.text(2.33, 3.85, "Usually still covered when his QB throws", color="#c8102e", fontsize=10, va="top")
ax.text(3.37, 1.45, "Open before his QB throws", color="#2e7d32", fontsize=10, ha="right")
lab = pd.concat([dd[dd["margin_s"] <= -0.2], dd[dd["player"].isin(["Marquise Brown", "Mark Andrews"])]])
nudge = {"Robert Tonyan": (6, 4), "Mike Williams": (6, -10), "Tyler Higbee": (-6, -12),
         "C.J. Uzomah": (-6, 6)}
for _, r in lab.iterrows():
    dx, dy = nudge.get(r["player"], (7, -3))
    ax.annotate(f"{r['player']} ({r['team']})", (r["xj"], r["open_by_s"]), xytext=(dx, dy),
                ha="right" if dx < 0 else "left", textcoords="offset points", fontsize=8)
ax.set_xlim(2.3, 3.45)
ax.set_ylim(lo, hi)
ax.set_xlabel("His QB's usual time to throw (team median, seconds after the snap)")
ax.set_ylabel("When he gets open (open on half his routes by this time, seconds)")
ax.set_title("Is he open before his own quarterback usually throws?\n"
             f"{len(d)} WRs and TEs with ≥{MIN_ROUTES} routes, 2021 Weeks 1–8; dot size = routes", loc="left", fontsize=12)
handles = [plt.Line2D([], [], marker="o", ls="", color=c, label=k) for k, c in COLORS.items()]
ax.legend(handles=handles, frameon=False, loc="lower left")
ax.spines[["top", "right"]].set_visible(False)
fig.tight_layout()
fig.savefig(f"{OUT}/qb_clock.png", dpi=150)
print("saved output/qb_clock.png")
