"""Receiver-Line Fit: tracking-based timing data for pockets and receivers.

Pocket collapse: first frame after the snap where any pass rusher is within RUSH_YD of the QB.
  Plays that end (throw / sack / run) before that are *censored* at the end of the play.
  Per team: S_team(t) = P(pocket still intact at t), Kaplan-Meier estimate.

Receiver open: first frame >= 0.5 s after the snap where the receiver is >= PAST_LOS yards past the
  line of scrimmage AND >= OPEN_YD yards from every coverage defender. Routes where his own QB threw
  before that are *censored* at the throw (we don't know if he would have gotten open later), so
  his own team's protection doesn't leak into his profile.
  Per player: F_player(t) = P(open by t), Kaplan-Meier estimate.

Fit Score(player, team) = sum over t of S_team(t) * dF_player(t)   (t up to 4 s)
  = probability he gets open while that team's pocket is still intact.
In-time rate = Fit / F_player(4 s) = of the times he gets open, the share with the pocket intact.

Run:  python src/fit_score.py [--open-yd 3] [--rush-yd 2] [--tag ""]
Outputs: output/fit_routes{tag}.csv, output/fit_pockets{tag}.csv, output/fit_scores{tag}.csv
"""
import argparse
import glob
import os

import numpy as np
import pandas as pd

ROOT = os.path.join(os.path.dirname(__file__), "..")
DATA = os.path.join(ROOT, "data-src", "data")
OUT = os.path.join(ROOT, "output")
PAST_LOS_YD, MIN_T, T_MAX = 3.0, 0.5, 4.0
GRID = np.round(np.arange(0, T_MAX + 0.001, 0.1), 1)
MIN_ROUTES = 150


def first_frame(t, names):
    return t[t["event"].isin(names)].groupby("playId")["frameId"].min()


def km_survival(times, events):
    """Kaplan-Meier S(t) on GRID; times rounded to 0.1 s."""
    times = np.round(np.asarray(times, float), 1)
    events = np.asarray(events, bool)
    s, out = 1.0, []
    for g in GRID:
        at_risk = (times >= g).sum()
        d = ((times == g) & events).sum()
        if at_risk > 0:
            s *= 1 - d / at_risk
        out.append(s)
    return np.array(out)


def extract(open_yd, rush_yd):
    plays = pd.read_csv(f"{DATA}/plays.csv")
    plays = plays[plays["passResult"].isin(["C", "I", "IN", "S", "R"])]
    pff = pd.read_csv(f"{DATA}/pffScoutingData.csv",
                      usecols=["gameId", "playId", "nflId", "pff_role", "pff_positionLinedUp"])
    pocket_rows, route_rows = [], []
    for f in sorted(glob.glob(f"{DATA}/tracking/*.csv")):
        t = pd.read_csv(f, usecols=["gameId", "playId", "nflId", "frameId", "x", "y", "event",
                                    "playDirection"])
        gid = t["gameId"].iat[0]
        snap = first_frame(t, ["ball_snap"]).combine_first(first_frame(t, ["autoevent_ballsnap"]))
        end = first_frame(t, ["pass_forward", "qb_sack", "qb_strip_sack", "run"]).combine_first(
            first_frame(t, ["autoevent_passforward"]))
        fr = pd.DataFrame({"snap": snap, "end": end}).dropna().reset_index()
        fr = fr[(fr["end"] > fr["snap"]) & fr["playId"].isin(plays.loc[plays["gameId"] == gid, "playId"])]
        fr["dur"] = (fr["end"] - fr["snap"]) / 10
        t = t.merge(fr, on="playId")
        t = t[(t["frameId"] >= t["snap"]) & (t["frameId"] <= t["end"])]
        t["xn"] = np.where(t["playDirection"] == "left", 120 - t["x"], t["x"])
        t["sec"] = (t["frameId"] - t["snap"]) / 10
        los = t[t["nflId"].isna() & (t["frameId"] == t["snap"])].set_index("playId")["xn"].rename("los")
        t = t.merge(pff[pff["gameId"] == gid], on=["gameId", "playId", "nflId"], how="left")

        qb = t[t["pff_role"] == "Pass"][["playId", "frameId", "x", "y"]]
        ru = t[t["pff_role"] == "Pass Rush"][["playId", "frameId", "x", "y", "sec"]]
        p = ru.merge(qb, on=["playId", "frameId"], suffixes=("", "_qb"))
        p["d"] = np.hypot(p["x"] - p["x_qb"], p["y"] - p["y_qb"])
        col = p[p["d"] <= rush_yd].groupby("playId")["sec"].min().rename("collapse")
        pk = fr.set_index("playId")[["dur"]].join(col)
        pk["event"] = pk["collapse"].notna()
        pk["time"] = pk["collapse"].fillna(pk["dur"])
        pk["gameId"] = gid
        pocket_rows.append(pk.reset_index()[["gameId", "playId", "time", "event", "dur"]])

        rr = t[t["pff_role"] == "Pass Route"][["playId", "nflId", "frameId", "x", "y", "xn", "sec"]]
        cv = t[t["pff_role"] == "Coverage"][["playId", "frameId", "x", "y"]]
        q = rr.merge(cv, on=["playId", "frameId"], suffixes=("", "_d"))
        q["d"] = np.hypot(q["x"] - q["x_d"], q["y"] - q["y_d"])
        sep = q.groupby(["playId", "nflId", "frameId", "sec", "xn"])["d"].min().reset_index()
        sep = sep.merge(los.reset_index(), on="playId")
        ok = sep[(sep["sec"] >= MIN_T) & (sep["xn"] - sep["los"] >= PAST_LOS_YD) & (sep["d"] >= open_yd)]
        ot = ok.groupby(["playId", "nflId"])["sec"].min().rename("open_t")
        allr = (t[t["pff_role"] == "Pass Route"][["playId", "nflId", "pff_positionLinedUp", "dur"]]
                .drop_duplicates(["playId", "nflId"]).set_index(["playId", "nflId"]).join(ot).reset_index())
        allr["gameId"] = gid
        route_rows.append(allr)

    team = plays[["gameId", "playId", "possessionTeam"]]
    pockets = pd.concat(pocket_rows).merge(team, on=["gameId", "playId"])
    routes = pd.concat(route_rows).merge(team, on=["gameId", "playId"])
    players = pd.read_csv(f"{DATA}/players.csv")[["nflId", "displayName", "officialPosition"]]
    routes = routes.merge(players, on="nflId")
    routes = routes[routes["officialPosition"].isin(["WR", "TE", "RB"])]
    routes["opened"] = routes["open_t"].notna()
    routes["obs_t"] = routes["open_t"].fillna(routes["dur"])  # censored at the end of the play
    return pockets, routes


def fit_scores(pockets, routes):
    S = pd.DataFrame({tm: km_survival(g["time"], g["event"]) for tm, g in pockets.groupby("possessionTeam")},
                     index=GRID)
    counts = routes.groupby("nflId").size()
    rows = []
    for pid, g in routes[routes["nflId"].isin(counts[counts >= MIN_ROUTES].index)].groupby("nflId"):
        F = 1 - km_survival(g["obs_t"], g["opened"])          # P(open by t)
        dF = np.diff(np.r_[0.0, F])
        med = GRID[np.argmax(F >= F[-1] / 2)] if F[-1] > 0 else np.nan  # median time among opens
        for tm in S.columns:
            fit = float((S[tm].values * dF).sum())
            rows.append({"nflId": pid, "player": g["displayName"].iat[0], "pos": g["officialPosition"].iat[0],
                         "own_team": g["possessionTeam"].mode().iat[0], "team": tm, "routes": len(g),
                         "open_by_4s": F[-1], "median_open_t": med, "fit": fit,
                         "in_time": fit / F[-1] if F[-1] > 0 else np.nan})
    return S, pd.DataFrame(rows)


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--open-yd", type=float, default=3.0)
    ap.add_argument("--rush-yd", type=float, default=2.0)
    ap.add_argument("--tag", default="")
    a = ap.parse_args()
    pockets, routes = extract(a.open_yd, a.rush_yd)
    S, fit = fit_scores(pockets, routes)
    routes.to_csv(f"{OUT}/fit_routes{a.tag}.csv", index=False)
    pockets.to_csv(f"{OUT}/fit_pockets{a.tag}.csv", index=False)
    S.to_csv(f"{OUT}/fit_pocket_curves{a.tag}.csv")
    fit.round(4).to_csv(f"{OUT}/fit_scores{a.tag}.csv", index=False)
    print(f"[open {a.open_yd} yd, rush {a.rush_yd} yd] plays {len(pockets):,} (collapse seen {pockets['event'].mean():.1%}), "
          f"routes {len(routes):,}, players {fit['nflId'].nunique()}")
