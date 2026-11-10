"""Build one row per route run: separation from the nearest coverage defender at the throw.

Also records where the player lined up (PFF alignment) and how far downfield he was at the throw,
so later steps can compare like with like.

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

ALIGN = {"LWR": "Outside WR", "RWR": "Outside WR",
         "SLWR": "Slot", "SRWR": "Slot", "SLoWR": "Slot", "SLiWR": "Slot", "SRoWR": "Slot", "SRiWR": "Slot",
         "TE-L": "Inline TE", "TE-R": "Inline TE", "TE-oL": "Inline TE", "TE-iL": "Inline TE",
         "TE-oR": "Inline TE", "TE-iR": "Inline TE",
         "HB": "Backfield", "HB-L": "Backfield", "HB-R": "Backfield", "FB": "Backfield", "FB-L": "Backfield",
         "FB-R": "Backfield"}

plays = pd.read_csv(f"{DATA}/plays.csv")
players = pd.read_csv(f"{DATA}/players.csv")
pff = pd.read_csv(f"{DATA}/pffScoutingData.csv",
                  usecols=["gameId", "playId", "nflId", "pff_role", "pff_positionLinedUp"])

# Only plays with a real throw and a Man/Zone label.
plays = plays[plays["passResult"].isin(["C", "I", "IN"])
              & plays["pff_passCoverageType"].isin(["Man", "Zone"])]

# --- Targeted receiver, parsed from playDescription (no target column exists) ---
# "... pass short left to C.Kupp to SEA 2 ..." / "... to A.St. Brown ..." / "... to M.Pittman. PENALTY ..."
pat = re.compile(r"pass (?:incomplete )?(?:short|deep)?\s*(?:left|right|middle)?\s*(?:to|intended for)\s+"
                 r"([A-Z][\w'-]*\.(?:St\.\s)?[A-Z][\w'-]+)")
plays = plays.assign(target_name=plays["playDescription"].str.extract(pat)[0])

routes = pff[pff["pff_role"] == "Pass Route"].merge(
    players[["nflId", "displayName", "officialPosition"]], on="nflId")
routes = routes[routes["officialPosition"].isin(["WR", "TE", "RB"])]
routes["align"] = routes["pff_positionLinedUp"].map(ALIGN)
routes = routes.dropna(subset=["align"])
cover = pff[pff["pff_role"] == "Coverage"][["gameId", "playId", "nflId"]]

routes = routes.merge(plays[["gameId", "playId", "pff_passCoverageType", "passResult",
                             "target_name", "playResult"]], on=["gameId", "playId"])
t_last = routes["target_name"].str.split(".").str[-1].str.strip()
r_last = routes["displayName"].str.split().str[-1]
routes["targeted"] = ((t_last == r_last)
                      & (routes["target_name"].str[0] == routes["displayName"].str[0]))
n_targets = routes.groupby(["gameId", "playId"])["targeted"].transform("sum")
routes = routes[n_targets == 1]  # keep throws whose target we can identify uniquely


def first_frame(t, names):
    return t[t["event"].isin(names)].groupby("playId")["frameId"].min()


rows = []
for f in sorted(glob.glob(f"{DATA}/tracking/*.csv")):
    t = pd.read_csv(f, usecols=["gameId", "playId", "nflId", "frameId", "x", "y", "event", "playDirection"])
    gid = t["gameId"].iat[0]
    snap = first_frame(t, ["ball_snap"]).combine_first(first_frame(t, ["autoevent_ballsnap"]))
    throw = first_frame(t, ["pass_forward"]).combine_first(first_frame(t, ["autoevent_passforward"]))
    fr = pd.DataFrame({"snap": snap, "throw": throw}).dropna().reset_index()
    fr = fr[fr["throw"] > fr["snap"]]
    t = t.merge(fr, on="playId")
    t["xn"] = np.where(t["playDirection"] == "left", 120 - t["x"], t["x"])  # offense always moves right
    los = t[t["nflId"].isna() & (t["frameId"] == t["snap"])].set_index("playId")["xn"].rename("los")
    t = t[t["frameId"] == t["throw"]]  # positions at the moment of the throw

    r = routes[routes["gameId"] == gid].merge(t, on=["gameId", "playId", "nflId"])
    d = cover[cover["gameId"] == gid].merge(t, on=["gameId", "playId", "nflId"])
    pair = r[["gameId", "playId", "nflId", "x", "y"]].merge(
        d[["playId", "x", "y"]], on="playId", suffixes=("", "_d"))
    pair["dist"] = np.hypot(pair["x"] - pair["x_d"], pair["y"] - pair["y_d"])
    sep = pair.groupby(["gameId", "playId", "nflId"])["dist"].min().rename("sep_at_throw")
    out = r.merge(sep.reset_index(), on=["gameId", "playId", "nflId"]).merge(los.reset_index(), on="playId")
    out["depth_at_throw"] = out["xn"] - out["los"]
    out["time_to_throw"] = (out["throw"] - out["snap"]) / 10
    rows.append(out)

df = pd.concat(rows, ignore_index=True)
df = df.rename(columns={"pff_passCoverageType": "coverage", "officialPosition": "pos"})
cols = ["gameId", "playId", "nflId", "displayName", "pos", "align", "coverage", "passResult",
        "targeted", "playResult", "time_to_throw", "depth_at_throw", "sep_at_throw"]
df[cols].to_csv(f"{OUT}/route_separation.csv", index=False)
n_throws = plays[plays["target_name"].notna()].shape[0]
print(f"routes: {len(df):,}  plays: {df[['gameId','playId']].drop_duplicates().shape[0]:,}  "
      f"players: {df['nflId'].nunique()}  (throws with a named target: {n_throws:,})")
print(df.groupby(["align", "coverage"])["sep_at_throw"].median().unstack().round(2).to_string())
print("targets per play:", df.groupby(["gameId", "playId"])["targeted"].sum().value_counts().to_dict())
