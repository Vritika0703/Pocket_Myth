"""Build one row per route run: separation from the nearest coverage defender at the throw.

Output: output/route_separation.csv
"""
import glob
import os
import re

import numpy as np
import pandas as pd

ROOT = os.path.join(os.path.dirname(__file__), "..")
DATA = os.path.join(ROOT, "data-src", "data")
OUT = os.path.join(ROOT, "output")
os.makedirs(OUT, exist_ok=True)

plays = pd.read_csv(f"{DATA}/plays.csv")
players = pd.read_csv(f"{DATA}/players.csv")
pff = pd.read_csv(f"{DATA}/pffScoutingData.csv", usecols=["gameId", "playId", "nflId", "pff_role"])

# Only plays with a real throw and a Man/Zone label.
plays = plays[plays["passResult"].isin(["C", "I", "IN"])
              & plays["pff_passCoverageType"].isin(["Man", "Zone"])]

# --- Targeted receiver, parsed from playDescription (no target column exists) ---
pat = re.compile(r"pass (?:incomplete )?(?:short|deep)?\s*(?:left|right|middle)?\s*"
                 r"(?:to|intended for)\s+([A-Z][\w'.-]*\.[\w' .-]+?)(?:\s|\.|,|$)")
plays = plays.assign(target_name=plays["playDescription"].str.extract(pat)[0].str.strip(" ."))

routes = pff[pff["pff_role"] == "Pass Route"].merge(
    players[["nflId", "displayName", "officialPosition"]], on="nflId")
routes = routes[routes["officialPosition"].isin(["WR", "TE", "RB"])]
cover = pff[pff["pff_role"] == "Coverage"][["gameId", "playId", "nflId"]]

routes = routes.merge(plays[["gameId", "playId", "pff_passCoverageType", "passResult",
                             "target_name", "playResult"]], on=["gameId", "playId"])
# target match: same first initial + last name as the abbreviated name ("C.Kupp")
t_last = routes["target_name"].str.split(".").str[-1].str.strip()
r_last = routes["displayName"].str.split().str[-1]
routes["targeted"] = ((t_last == r_last)
                      & (routes["target_name"].str[0] == routes["displayName"].str[0]))
has_target = routes.groupby(["gameId", "playId"])["targeted"].transform("any")
routes = routes[has_target]  # drop the ~7% of throws whose target we can't identify


def first_frame(t, names):
    f = t[t["event"].isin(names)].groupby("playId")["frameId"].min()
    return f


rows = []
for f in sorted(glob.glob(f"{DATA}/tracking/*.csv")):
    t = pd.read_csv(f, usecols=["gameId", "playId", "nflId", "frameId", "x", "y", "event"])
    gid = t["gameId"].iat[0]
    # manual events first; fall back to autoevents only if the manual tag is missing
    snap = first_frame(t, ["ball_snap"]).combine_first(first_frame(t, ["autoevent_ballsnap"]))
    throw = first_frame(t, ["pass_forward"]).combine_first(first_frame(t, ["autoevent_passforward"]))
    fr = pd.DataFrame({"snap": snap, "throw": throw}).dropna().reset_index()
    fr = fr[fr["throw"] > fr["snap"]]
    t = t.merge(fr, on="playId")
    t = t[t["frameId"] == t["throw"]]  # positions at the moment of the throw

    r = routes[routes["gameId"] == gid].merge(t, on=["gameId", "playId", "nflId"])
    d = cover[cover["gameId"] == gid].merge(t, on=["gameId", "playId", "nflId"])
    pair = r[["gameId", "playId", "nflId", "x", "y"]].merge(
        d[["playId", "x", "y"]], on="playId", suffixes=("", "_d"))
    pair["dist"] = np.hypot(pair["x"] - pair["x_d"], pair["y"] - pair["y_d"])
    sep = pair.groupby(["gameId", "playId", "nflId"])["dist"].min().rename("sep_at_throw")
    out = r.drop(columns=["x", "y", "event", "frameId"]).merge(
        sep.reset_index(), on=["gameId", "playId", "nflId"])
    out["time_to_throw"] = (out["throw"] - out["snap"]) / 10
    rows.append(out)

df = pd.concat(rows, ignore_index=True)
df = df.rename(columns={"pff_passCoverageType": "coverage", "officialPosition": "pos"})
cols = ["gameId", "playId", "nflId", "displayName", "pos", "coverage", "passResult",
        "targeted", "playResult", "time_to_throw", "sep_at_throw"]
df[cols].to_csv(f"{OUT}/route_separation.csv", index=False)
print(f"routes: {len(df):,}  plays: {df[['gameId','playId']].drop_duplicates().shape[0]:,}  "
      f"players: {df['nflId'].nunique()}")
print(df.groupby(["pos", "coverage"])["sep_at_throw"].describe().round(2).to_string())
print("targets per play (should be 1):",
      df.groupby(["gameId", "playId"])["targeted"].sum().value_counts().to_dict())
