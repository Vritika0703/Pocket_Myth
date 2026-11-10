"""Receiver-Line Fit analysis: are late-opening receivers hurt more by a weak offensive line?

Reads the outputs of fit_score.py. Headline uses WRs and TEs (RBs start behind the line, so their
"open time" isn't comparable; they are reported separately).

1. Model-based: in-time rate behind the 5 best vs 5 worst pocket-keeping teams, by open-time group.
2. Reality check on what actually happened on each team's own plays (not model-based):
   do late openers on weak-line teams really get open before the throw less often, and get targeted
   and complete fewer passes, compared with early openers? (difference-in-differences, game bootstrap)
3. Line-strength check: does our tracking-based pocket measure agree with PFF's pressure charting?

Run: python src/fit_deep.py [--tag ""]      Outputs: output/fit_timing.png, output/fit_best_teams.csv
"""
import argparse
import os

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

ROOT = os.path.join(os.path.dirname(__file__), "..")
OUT = os.path.join(ROOT, "output")
DATA = os.path.join(ROOT, "data-src", "data")


def summarize(tag="", verbose=True):
    f = pd.read_csv(f"{OUT}/fit_scores{tag}.csv")
    S = pd.read_csv(f"{OUT}/fit_pocket_curves{tag}.csv", index_col=0)
    S.index = np.round(S.index.astype(float), 1)
    line = S.loc[2.5].sort_values()          # P(pocket intact at 2.5 s)
    worst5, best5 = list(line.index[:5]), list(line.index[-5:])
    p = f.drop_duplicates("nflId").set_index("player")[["pos", "median_open_t", "open_by_4s", "own_team"]]
    p["best"] = f[f["team"].isin(best5)].groupby("player")["in_time"].mean()
    p["worst"] = f[f["team"].isin(worst5)].groupby("player")["in_time"].mean()
    p["loss"] = (p["best"] - p["worst"]) * 100
    wt = p[p["pos"].isin(["WR", "TE"])].copy()
    wt["grp"] = pd.qcut(wt["median_open_t"].rank(method="first"), 3, labels=["Early", "Mid", "Late"])
    grp = wt.groupby("grp", observed=True)[["median_open_t", "loss"]].mean()
    res = {"early_loss": grp.loc["Early", "loss"], "late_loss": grp.loc["Late", "loss"],
           "corr": wt["median_open_t"].corr(wt["loss"]), "best5": best5, "worst5": worst5}
    if verbose:
        print("best-5 lines:", best5, " worst-5:", worst5)
        print(grp.round(2).to_string())
        print("WR+TE corr(open time, loss):", round(res["corr"], 2),
              "| WR only:", round(wt[wt.pos == "WR"]["median_open_t"].corr(wt[wt.pos == "WR"]["loss"]), 2))
        print("RBs (separate):\n", p[p["pos"] == "RB"][["median_open_t", "best", "worst", "loss"]].round(2).to_string())
    return f, S, line, p, wt, grp, res


def reality_check(tag, wt, line, n_boot=500):
    """Own-team plays only. Late vs early openers x weak vs strong own line."""
    r = pd.read_csv(f"{OUT}/fit_routes{tag}.csv")
    sep = pd.read_csv(f"{OUT}/route_separation.csv")[["gameId", "playId", "nflId", "targeted", "passResult"]]
    r = r.merge(wt[["grp"]].reset_index().merge(
        pd.read_csv(f"{OUT}/fit_scores{tag}.csv")[["player", "nflId"]].drop_duplicates(), on="player"),
        on="nflId")
    r = r[r["grp"].isin(["Early", "Late"])]
    r["weak_line"] = r["possessionTeam"].isin(line.index[: len(line) // 2])
    r = r.merge(sep, on=["gameId", "playId", "nflId"], how="left")
    r["in_time"] = r["opened"].astype(float)                    # open before his QB threw / play ended
    r["tgt"] = r["targeted"].astype(float)                      # NaN where play had no identified target
    r["catch"] = np.where(r["targeted"].isna(), np.nan,
                          ((r["targeted"] == True) & (r["passResult"] == "C")).astype(float))

    def did(d, col):
        m = d.groupby(["grp", "weak_line"], observed=True)[col].mean()
        return ((m[("Late", False)] - m[("Late", True)]) - (m[("Early", False)] - m[("Early", True)])) * 100, m

    out = {}
    games = r["gameId"].unique()
    rng = np.random.default_rng(0)
    by_game = {g: d for g, d in r.groupby("gameId")}
    for col in ["in_time", "tgt", "catch"]:
        est, m = did(r, col)
        boots = []
        for _ in range(n_boot):
            samp = pd.concat([by_game[g] for g in rng.choice(games, len(games))])
            boots.append(did(samp, col)[0])
        lo, hi = np.percentile(boots, [2.5, 97.5])
        out[col] = {"did": est, "lo": lo, "hi": hi, "cells": (m * 100).round(1)}
    return out


def pff_line_strength():
    """Team pass protection from PFF charting: 1 - share of dropbacks with a hit, hurry or sack."""
    pff = pd.read_csv(f"{DATA}/pffScoutingData.csv")
    plays = pd.read_csv(f"{DATA}/plays.csv")[["gameId", "playId", "possessionTeam"]]
    pr = (pff[pff["pff_role"] == "Pass Rush"].groupby(["gameId", "playId"])[["pff_hit", "pff_hurry", "pff_sack"]]
          .max().max(axis=1).rename("pressure").reset_index().merge(plays))
    return (1 - pr.groupby("possessionTeam")["pressure"].mean()).sort_values()


def line_check(line):
    plays = pd.read_csv(f"{DATA}/plays.csv")[["gameId", "playId", "possessionTeam"]]
    pff_line = pff_line_strength()
    sep = pd.read_csv(f"{OUT}/route_separation.csv").drop_duplicates(["gameId", "playId"]).merge(plays)
    ttt = sep.groupby("possessionTeam")["time_to_throw"].median()
    return (line.rank().corr(pff_line.reindex(line.index).rank()),
            line.rank().corr(ttt.reindex(line.index).rank()))


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--tag", default="")
    a = ap.parse_args()
    f, S, line, p, wt, grp, res = summarize(a.tag)

    rho_pff, rho_ttt = line_check(line)
    print(f"\nLine check: Spearman(pocket intact @2.5s, PFF pressure-free rate) = {rho_pff:.2f}; "
          f"vs QB median time-to-throw = {rho_ttt:.2f}")

    rcs = {"Weak line = tracking pocket": reality_check(a.tag, wt, line),
           "Weak line = PFF pressure rate": reality_check(a.tag, wt, pff_line_strength())}
    for name, rc in rcs.items():
        print(f"\nReality check [{name}] (late-vs-early extra drop on weak-line teams, points):")
        for k, v in rc.items():
            print(f"  {k:8s} DiD = {v['did']:+.1f}  95% CI [{v['lo']:+.1f}, {v['hi']:+.1f}]  {v['cells'].to_dict()}")

    # best / worst team fits per WR & TE (latest openers first)
    rows = []
    for player, g in f[f["pos"].isin(["WR", "TE"])].groupby("player"):
        g = g.sort_values("in_time", ascending=False)
        rows.append({"player": player, "pos": g["pos"].iat[0], "own_team": g["own_team"].iat[0],
                     "median_open_s": g["median_open_t"].iat[0],
                     "best_3_teams": ", ".join(g["team"].head(3)),
                     "best_in_time_%": round(100 * g["in_time"].head(3).mean(), 1),
                     "worst_3_teams": ", ".join(g["team"].tail(3)),
                     "worst_in_time_%": round(100 * g["in_time"].tail(3).mean(), 1)})
    bt = pd.DataFrame(rows).sort_values("median_open_s", ascending=False)
    bt["loss_pts"] = (bt["best_in_time_%"] - bt["worst_in_time_%"]).round(1)
    bt.to_csv(f"{OUT}/fit_best_teams.csv", index=False)
    print("\n", bt.head(8).to_string(index=False))

    # ---------- figure ----------
    fig, (a1, a2) = plt.subplots(1, 2, figsize=(14, 5.6), gridspec_kw={"width_ratios": [1.4, 1]})
    s = wt.sort_values("median_open_t")
    colors = {"WR": "#2a6fdb", "TE": "#e07b24"}
    for pos, d in s.groupby("pos"):
        a1.scatter(d["median_open_t"], d["loss"], s=34, color=colors[pos], label=pos, alpha=0.8,
                   edgecolor="white", lw=0.6)
    m, b = np.polyfit(s["median_open_t"], s["loss"], 1)
    xs = np.linspace(s["median_open_t"].min(), s["median_open_t"].max(), 10)
    a1.plot(xs, m * xs + b, color="#444", lw=1.5, ls="--")
    for i, name in enumerate(s.nlargest(5, "loss").index):
        a1.annotate(name, (s.loc[name, "median_open_t"], s.loc[name, "loss"]),
                    xytext=(-6, 8) if i % 2 else (6, -12), ha="right" if i % 2 else "left",
                    textcoords="offset points", fontsize=8)
    a1.set_xlabel("When he usually gets open (median seconds after the snap)")
    a1.set_ylabel("Points lost: best-5 → worst-5 pass-blocking lines\n(share of his opens with the pocket intact)")
    a1.set_title(f"Model prediction: later openers lose more (r = {res['corr']:.2f})", loc="left")
    a1.legend(frameon=False)
    a1.spines[["top", "right"]].set_visible(False)

    lab = {"in_time": "Got open\nbefore the throw", "tgt": "Was\ntargeted", "catch": "Caught\nthe ball"}
    keys = list(lab)
    xs = np.arange(len(keys))
    for j, ((name, rc), c) in enumerate(zip(rcs.items(), ["#0c447c", "#7fb8e6"])):
        y = np.array([rc[k]["did"] for k in keys])
        err = np.array([[rc[k]["did"] - rc[k]["lo"] for k in keys], [rc[k]["hi"] - rc[k]["did"] for k in keys]])
        a2.bar(xs + (j - 0.5) * 0.38, y, width=0.38, yerr=err, capsize=4, color=c, label=name)
    a2.set_xticks(xs, [lab[k] for k in keys])
    a2.axhline(0, color="#333", lw=1)
    a2.set_ylabel("Extra drop for late openers on weak-line teams\nvs early openers (points, ±95% CI)")
    a2.set_title("Reality: no extra penalty on actual plays", loc="left")
    a2.legend(frameon=False, fontsize=8, loc="upper center", bbox_to_anchor=(0.5, -0.16), ncol=1)
    a2.spines[["top", "right"]].set_visible(False)
    fig.suptitle("Receiver-Line Fit: the timing model says late openers need a strong line; real plays say they don't  (WR & TE, 2021 Wk 1–8)",
                 x=0.01, ha="left", fontsize=13)
    fig.tight_layout()
    fig.savefig(f"{OUT}/fit_timing.png", dpi=150)
    print("saved output/fit_timing.png")
