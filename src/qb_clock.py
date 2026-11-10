"""Is each receiver open before HIS OWN quarterback usually throws?

Uses output/fit_routes.csv and output/fit_pockets.csv from fit_score.py.
  open-by time  = time after the snap by which he has been open on half his routes
                  (Kaplan-Meier; routes cut short by the throw count as unknown after that point)
  QB clock      = his team's median time from snap to the end of the dropback
  open at clock = share of his routes on which he is open by his QB's usual throw time

Output: output/open_vs_qb_clock.csv
"""
import os
import sys

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(__file__))
from fit_score import GRID, MIN_ROUTES, km_survival  # noqa: E402

OUT = os.path.join(os.path.dirname(__file__), "..", "output")

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
