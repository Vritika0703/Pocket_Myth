"""Pocket_Myth: Is this receiver good, and would he fit our quarterback?

Part 1 - Player profile: how well does he get open, and against which coverage?
  Man score / Zone score = average separation at the throw vs a typical player in the same alignment
  (outside WR, slot, inline TE, backfield), same coverage and time to throw, shrunk for sample size
  (empirical Bayes). Plus his timing: by when he's open on half his routes.

Part 2 - Team fit: if a team adds him, how often is he open before THAT team's QB throws?
  QB fit(player, team) = average over the team's dropbacks of P(player open by the moment that
  dropback ended), using the player's open-time curve (Kaplan-Meier from fit_score.py).

Validation - QB changes inside Weeks 1-8 (same receivers, different QB):
  learn a receiver's open-time curve with QB A, predict his open-before-throw rate with QB B from
  QB B's dropback times only, and compare the predicted change with the actual change.

Inputs: output/route_separation.csv, output/fit_routes.csv, output/fit_pockets.csv
Outputs: output/player_profiles.csv, output/qb_fit_matrix.csv, output/qb_change_validation.csv,
         output/profile_man_zone.png, output/qb_fit.png, output/qb_change_validation.png
"""
import os
import sys

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(__file__))
from fit_score import GRID, MIN_ROUTES, km_survival  # noqa: E402

ROOT = os.path.join(os.path.dirname(__file__), "..")
OUT = os.path.join(ROOT, "output")
DATA = os.path.join(ROOT, "data-src", "data")
COLORS = {"WR": "#2a6fdb", "TE": "#e07b24", "RB": "#2e9e5b"}
rng = np.random.default_rng(0)


def open_curve(g):
    """P(open by t) on GRID from a set of routes (censored at the end of the play)."""
    return 1 - km_survival(g["obs_t"], g["opened"])


def at(F, times):
    """Evaluate a GRID curve at arbitrary times (seconds)."""
    idx = np.clip(np.round(np.asarray(times, float) / 0.1).astype(int), 0, len(GRID) - 1)
    return F[idx]


# ------------------------------------------------------------------ Part 1: profile
df = pd.read_csv(f"{OUT}/route_separation.csv")
df["exp_sep"] = np.nan
for _, g in df.groupby(["align", "coverage"]):
    b, a = np.polyfit(g["time_to_throw"], g["sep_at_throw"], 1)
    df.loc[g.index, "exp_sep"] = a + b * g["time_to_throw"]
df["soe"] = df["sep_at_throw"] - df["exp_sep"]


def shrunk_scores(sub, min_n):
    s = sub.groupby(["nflId", "displayName", "pos"])["soe"].agg(["mean", "std", "size"]).reset_index()
    s = s[s["size"] >= min_n].copy()
    s["se"] = s["std"] / np.sqrt(s["size"])
    tau2 = max(s["mean"].var() - (s["se"] ** 2).mean(), 1e-6)
    s["score"] = tau2 / (tau2 + s["se"] ** 2) * s["mean"]
    return s.set_index("nflId")


man = shrunk_scores(df[df["coverage"] == "Man"], 40)
zone = shrunk_scores(df[df["coverage"] == "Zone"], 100)

routes = pd.read_csv(f"{OUT}/fit_routes.csv")
counts = routes.groupby("nflId").size()
routes_q = routes[routes["nflId"].isin(counts[counts >= MIN_ROUTES].index)]
curves = {pid: open_curve(g) for pid, g in routes_q.groupby("nflId")}

prof = man[["displayName", "pos", "size", "score"]].rename(columns={"size": "man_routes", "score": "man_score"})
prof = prof.join(zone[["size", "score"]].rename(columns={"size": "zone_routes", "score": "zone_score"}), how="inner")
prof = prof[prof.index.isin(curves)].copy()
prof["open_by_s"] = [GRID[np.argmax(curves[p] >= 0.5)] if curves[p][-1] >= 0.5 else np.nan for p in prof.index]
prof["open_by_4s"] = [curves[p][-1] for p in prof.index]
prof["own_team"] = routes_q.groupby("nflId")["possessionTeam"].agg(lambda s: s.mode().iat[0]).reindex(prof.index)


def label(r):
    m, z = r["man_score"] > 0, r["zone_score"] > 0
    return {(True, True): "Beats both", (True, False): "Man specialist",
            (False, True): "Zone specialist", (False, False): "Below average vs both"}[(m, z)]


prof["type"] = prof.apply(label, axis=1)
print(f"PART 1: profiled players: {len(prof)}  corr(man score, zone score) = "
      f"{prof['man_score'].corr(prof['zone_score']):.2f}")
print(prof["type"].value_counts().to_string())

# ------------------------------------------------------------------ Part 2: QB fit
pockets = pd.read_csv(f"{OUT}/fit_pockets.csv")
team_times = {t: g["dur"].values for t, g in pockets.groupby("possessionTeam")}
qb_clock = pockets.groupby("possessionTeam")["dur"].median()
fit = pd.DataFrame({t: [at(curves[p], tt).mean() for p in prof.index] for t, tt in team_times.items()},
                   index=prof.index)
prof["fit_own"] = [fit.loc[p, prof.loc[p, "own_team"]] for p in prof.index]
prof["best_team"] = fit.idxmax(axis=1)
prof["fit_best"] = fit.max(axis=1)
prof["worst_team"] = fit.idxmin(axis=1)
prof["fit_worst"] = fit.min(axis=1)
prof["fit_range"] = prof["fit_best"] - prof["fit_worst"]
print(f"\nPART 2: QB fit range across teams: median {prof['fit_range'].median()*100:.1f} pts, "
      f"max {prof['fit_range'].max()*100:.1f} pts")
print("teams by average fit:", (fit.mean().sort_values() * 100).round(1).to_dict())
prof.round(3).to_csv(f"{OUT}/player_profiles.csv")
fit.assign(player=prof["displayName"]).set_index("player").round(3).to_csv(f"{OUT}/qb_fit_matrix.csv")

# ------------------------------------------------------------------ Validation: QB changes
pff = pd.read_csv(f"{DATA}/pffScoutingData.csv", usecols=["gameId", "playId", "nflId", "pff_role"])
players = pd.read_csv(f"{DATA}/players.csv")[["nflId", "displayName"]]
qb = (pff[pff["pff_role"] == "Pass"][["gameId", "playId", "nflId"]].merge(players, on="nflId")
      .rename(columns={"displayName": "qb"})[["gameId", "playId", "qb"]])
pk = pockets.merge(qb, on=["gameId", "playId"])
qb_n = pk.groupby(["possessionTeam", "qb"]).size()
qbs = qb_n[qb_n >= 40].reset_index()[["possessionTeam", "qb"]]
qbs = qbs[qbs.groupby("possessionTeam")["qb"].transform("size") >= 2]
qb_times = {q: g["dur"].values for q, g in pk[pk["qb"].isin(qbs["qb"])].groupby("qb")}

tg = pd.read_csv(f"{OUT}/route_separation.csv")[["gameId", "playId", "nflId", "targeted"]]
rq = routes.merge(qb, on=["gameId", "playId"]).merge(qbs, on=["possessionTeam", "qb"])
rq = rq.merge(tg, on=["gameId", "playId", "nflId"], how="left")
rows = []
for (team, pid), g in rq.groupby(["possessionTeam", "nflId"]):
    by_qb = {q: d for q, d in g.groupby("qb") if len(d) >= 30}
    if len(by_qb) < 2:
        continue
    a, b = sorted(by_qb, key=lambda q: -len(by_qb[q]))[:2]     # A = QB he played more with
    FA = open_curve(by_qb[a])                                     # learned with QB A only
    pred_a, pred_b = at(FA, qb_times[a]).mean(), at(FA, qb_times[b]).mean()
    act_a, act_b = by_qb[a]["opened"].mean(), by_qb[b]["opened"].mean()
    rows.append({"team": team, "player": g["displayName"].iat[0], "pos": g["officialPosition"].iat[0],
                 "qb_A": a, "qb_B": b, "routes_A": len(by_qb[a]), "routes_B": len(by_qb[b]),
                 "clock_A": np.median(qb_times[a]), "clock_B": np.median(qb_times[b]),
                 "pred_change": (pred_b - pred_a) * 100, "actual_change": (act_b - act_a) * 100,
                 "target_change": (by_qb[b]["targeted"].mean() - by_qb[a]["targeted"].mean()) * 100})
val = pd.DataFrame(rows)
val.round(3).to_csv(f"{OUT}/qb_change_validation.csv", index=False)


def boot_corr(x, y, n=2000):
    idx = rng.integers(0, len(x), (n, len(x)))
    return np.percentile([np.corrcoef(x[i], y[i])[0, 1] for i in idx], [2.5, 97.5])


x, y = val["pred_change"].values, val["actual_change"].values
r_open, ci_open = np.corrcoef(x, y)[0, 1], boot_corr(x, y)
slope = np.polyfit(x, y, 1)[0]
sign = (np.sign(x) == np.sign(y)).mean()
mae_model, mae_null = np.abs(y - x).mean(), np.abs(y).mean()
p_perm = np.mean([np.corrcoef(x, rng.permutation(y))[0, 1] >= r_open for _ in range(5000)])
r_sp = val["pred_change"].corr(val["actual_change"], method="spearman")
big = val[(val["routes_A"] >= 50) & (val["routes_B"] >= 50)]
r_big = big["pred_change"].corr(big["actual_change"])
yt = val["target_change"].values
r_tgt, ci_tgt = np.corrcoef(x, yt)[0, 1], boot_corr(x, yt)
print(f"\nVALIDATION: {len(val)} receivers across {val['team'].nunique()} teams with a QB change")
print(f"  open-before-throw: r = {r_open:.2f} [{ci_open[0]:.2f}, {ci_open[1]:.2f}], slope {slope:.2f}, "
      f"same direction {sign:.0%}, error {mae_model:.1f} pts vs {mae_null:.1f} pts if we assumed no change")
print(f"  rank r = {r_sp:.2f}, permutation p = {p_perm:.4f}, players with 50+ routes under both QBs: "
      f"n = {len(big)}, r = {r_big:.2f}")
print(f"  target rate:       r = {r_tgt:.2f} [{ci_tgt[0]:.2f}, {ci_tgt[1]:.2f}]")

# ------------------------------------------------------------------ Charts
# Part 1
fig, ax = plt.subplots(figsize=(10, 7.5))
ax.scatter(prof["zone_score"], prof["man_score"], s=prof["man_routes"] * 2.2, c=prof["pos"].map(COLORS),
           alpha=0.75, edgecolor="white", lw=0.7)
ax.axhline(0, color="#999", ls="--", lw=1)
ax.axvline(0, color="#999", ls="--", lw=1)
lab = pd.concat([prof.nlargest(4, "man_score"), prof.nlargest(4, "zone_score"), prof.nsmallest(3, "man_score"),
                 prof.nsmallest(2, "zone_score")])
lab = lab[~lab.index.duplicated()]
for _, r in lab.iterrows():
    left = r["displayName"] in ("Mike Evans",)
    ax.annotate(r["displayName"], (r["zone_score"], r["man_score"]), xytext=(-5, -12) if left else (5, 4),
                ha="right" if left else "left", textcoords="offset points", fontsize=8.5)
xl, yl = ax.get_xlim(), ax.get_ylim()
for x0, y0, t, ha, va in [(xl[1], yl[1], "BEATS BOTH", "right", "top"), (xl[0], yl[1], "MAN SPECIALIST", "left", "top"),
                          (xl[1], yl[0], "ZONE SPECIALIST", "right", "bottom"),
                          (xl[0], yl[0], "BELOW AVERAGE VS BOTH", "left", "bottom")]:
    ax.text(x0, y0, t, ha=ha, va=va, fontsize=10, fontweight="bold", color="#888")
ax.set_xlabel("Zone score: separation over expected vs ZONE (yards, shrunk for sample size)")
ax.set_ylabel("Man score: separation over expected vs MAN (yards, shrunk)")
ax.set_title("Part 1: How well does he get open, and against which coverage?\n"
             f"{len(prof)} receivers vs players in the same alignment; bubble size = man routes; 2021 Weeks 1–8",
             loc="left", fontsize=12)
handles = [plt.Line2D([], [], marker="o", ls="", color=c, label=k) for k, c in COLORS.items()]
ax.legend(handles=[h for h in handles if h.get_label() in set(prof["pos"])], frameon=False, loc="center left")
ax.spines[["top", "right"]].set_visible(False)
fig.tight_layout()
fig.savefig(f"{OUT}/profile_man_zone.png", dpi=150)

# Part 2: ranges across the 32 teams for the 18 players whose fit depends most on the QB
sel = prof.sort_values("fit_range", ascending=False).head(18).iloc[::-1]
fig, ax = plt.subplots(figsize=(11, 7.5))
for i, (pid, r) in enumerate(sel.iterrows()):
    ax.plot([r["fit_worst"] * 100, r["fit_best"] * 100], [i, i], color="#ccc", lw=6, solid_capstyle="round", zorder=1)
    ax.scatter(r["fit_worst"] * 100, i, color="#c8102e", s=40, zorder=2)
    ax.scatter(r["fit_best"] * 100, i, color="#2e7d32", s=40, zorder=2)
    ax.scatter(r["fit_own"] * 100, i, color="black", marker="|", s=250, zorder=3)
    ax.text(r["fit_worst"] * 100 - 0.6, i, r["worst_team"], ha="right", va="center", fontsize=8, color="#c8102e")
    ax.text(r["fit_best"] * 100 + 0.6, i, r["best_team"], ha="left", va="center", fontsize=8, color="#2e7d32")
ax.set_yticks(range(len(sel)), [f"{r['displayName']} ({r['pos']}, {r['own_team']})" for _, r in sel.iterrows()],
              fontsize=9)
ax.set_xlabel("Open before the throw: share of that team's dropbacks on which he'd already be open")
ax.xaxis.set_major_formatter(lambda v, _: f"{v:.0f}%")
ax.set_title("Part 2: If a team adds him, how often is he open before that team's QB throws?\n"
             "18 receivers whose fit depends most on the QB. Red = worst fit, green = best fit,\n"
             "black tick = his current team", loc="left", fontsize=12)
ax.spines[["top", "right"]].set_visible(False)
fig.tight_layout()
fig.savefig(f"{OUT}/qb_fit.png", dpi=150)

# Validation
fig, ax = plt.subplots(figsize=(7.5, 6.5))
ax.scatter(val["pred_change"], val["actual_change"], c=val["pos"].map(COLORS), s=50, edgecolor="white")
m_, b_ = np.polyfit(x, y, 1)
xs_ = np.linspace(x.min(), x.max(), 10)
ax.plot(xs_, m_ * xs_ + b_, color="#444", ls="--", lw=1.2)
ax.axhline(0, color="#ddd", lw=0.8)
ax.axvline(0, color="#ddd", lw=0.8)
ax.set_xlabel("Predicted change in open-before-throw rate (points)\n(from his routes with QB A + QB B's clock)")
ax.set_ylabel("Actual change with QB B (points)")
ax.set_title(f"Validation: {len(val)} receivers who played with two QBs in Weeks 1–8\n"
             f"r = {r_open:.2f} (95% CI {ci_open[0]:.2f} to {ci_open[1]:.2f}), permutation p = {p_perm:.3f}; dashed = fitted line",
             loc="left", fontsize=11)
ax.legend(handles=[h for h in handles if h.get_label() in set(val["pos"])], frameon=False, loc="upper left")
ax.spines[["top", "right"]].set_visible(False)
fig.tight_layout()
fig.savefig(f"{OUT}/qb_change_validation.png", dpi=150)
print("saved charts")
