"""Step 2: confirm the traps found in explore.py."""
import glob
import os
import re

import pandas as pd

DATA = os.path.join(os.path.dirname(__file__), "..", "data-src", "data")
plays = pd.read_csv(f"{DATA}/plays.csv")
players = pd.read_csv(f"{DATA}/players.csv")
pff = pd.read_csv(f"{DATA}/pffScoutingData.csv")
files = sorted(glob.glob(f"{DATA}/tracking/*.csv"))

# --- Trap A: how many frames exist after the throw? ---
t = pd.concat(pd.read_csv(f, usecols=["gameId", "playId", "frameId", "event"]) for f in files[:10])
t["event"] = t["event"].replace("None", pd.NA)
fr = t.groupby(["gameId", "playId"]).agg(last=("frameId", "max"))
pf = (t[t["event"] == "pass_forward"].groupby(["gameId", "playId"])["frameId"].min()
      .rename("pf"))
snap = (t[t["event"] == "ball_snap"].groupby(["gameId", "playId"])["frameId"].min()
        .rename("snap"))
fr = fr.join(pf).join(snap)
fr["after_throw"] = fr["last"] - fr["pf"]
fr["snap_to_throw_s"] = (fr["pf"] - fr["snap"]) / 10
print("frames after pass_forward (10 games):")
print(fr["after_throw"].describe().round(1).to_string())
print("snap->throw seconds:")
print(fr["snap_to_throw_s"].describe().round(2).to_string())

# --- Trap B: event 'None' is a string, and autoevents duplicate real events ---
raw = pd.read_csv(files[0], usecols=["event"])
print("\nevent 'None' string rows:", (raw["event"] == "None").sum(), " NaN rows:", raw["event"].isna().sum())

# --- Workaround: parse targeted receiver from playDescription ---
pat = re.compile(r"pass (?:short|deep|incomplete short|incomplete deep|incomplete)?\s*"
                 r"(?:left|right|middle)?\s*(?:to|intended for)\s+([A-Z][\w'.-]*\.[\w' .-]+?)(?:\s|\.|,|$)")
throws = plays[plays["passResult"].isin(["C", "I", "IN"])].copy()
throws["target_name"] = throws["playDescription"].str.extract(pat)[0].str.strip(" .")
print(f"\nthrows: {len(throws)}  target name parsed: {throws['target_name'].notna().mean():.1%}")
print(throws[["playDescription", "target_name"]].sample(6, random_state=1).to_string())

# match name -> route runner on that play (abbrev 'C.Lamb' vs 'CeeDee Lamb')
routes = pff[pff["pff_role"] == "Pass Route"].merge(
    players[["nflId", "displayName", "officialPosition"]], on="nflId")
routes["last"] = routes["displayName"].str.split().str[-1]
routes["first_init"] = routes["displayName"].str[0]
throws["t_last"] = throws["target_name"].str.split(".").str[-1].str.strip()
throws["t_init"] = throws["target_name"].str[0]
m = throws.merge(routes, left_on=["gameId", "playId", "t_last", "t_init"],
                 right_on=["gameId", "playId", "last", "first_init"], how="left")
per_play = m.groupby(["gameId", "playId"])["nflId"].nunique()
print("\ntarget matched to exactly one route runner:", f"{(per_play == 1).mean():.1%}",
      " ambiguous (>1):", (per_play > 1).sum(), " unmatched:", (per_play == 0).sum())
print(m.dropna(subset=["nflId"])["officialPosition"].value_counts().to_string())

# --- Trap C: coverage Man/Zone labels on throws ---
print("\ncoverage type on throws:")
print(throws["pff_passCoverageType"].value_counts(dropna=False).to_string())
