"""Step 1: orient on the dataset and check for data traps before any analysis."""
import glob
import os

import pandas as pd

DATA = os.path.join(os.path.dirname(__file__), "..", "data-src", "data")

games = pd.read_csv(f"{DATA}/games.csv")
plays = pd.read_csv(f"{DATA}/plays.csv")
players = pd.read_csv(f"{DATA}/players.csv")
pff = pd.read_csv(f"{DATA}/pffScoutingData.csv")


def section(title):
    print(f"\n{'=' * 8} {title} {'=' * 8}")


section("SHAPES + KEYS")
for name, df, key in [
    ("games", games, ["gameId"]),
    ("plays", plays, ["gameId", "playId"]),
    ("players", players, ["nflId"]),
    ("pff", pff, ["gameId", "playId", "nflId"]),
]:
    dupes = df.duplicated(key).sum()
    print(f"{name:8s} rows={len(df):>7,}  cols={df.shape[1]:>3}  dup keys on {key}: {dupes}")

section("COLUMNS")
print("plays:", list(plays.columns))
print("pff:  ", list(pff.columns))
print("players:", list(players.columns))

section("PLAYS: passResult / coverage / dropback")
print(plays["passResult"].value_counts(dropna=False).to_string())
print(plays["pff_passCoverage"].value_counts(dropna=False).to_string())
if "pff_passCoverageType" in plays:
    print(plays["pff_passCoverageType"].value_counts(dropna=False).to_string())
print(plays["dropBackType"].value_counts(dropna=False).head(10).to_string())

section("PFF roles and route runners by position")
print(pff["pff_role"].value_counts(dropna=False).to_string())
routes = pff[pff["pff_role"] == "Pass Route"].merge(
    players[["nflId", "officialPosition"]], on="nflId", how="left"
)
print(routes["officialPosition"].value_counts(dropna=False).to_string())
print("route-runner rows:", len(routes), " unique players:", routes["nflId"].nunique())

section("JOIN CHECKS")
print("plays without a game:", (~plays["gameId"].isin(games["gameId"])).sum())
pff_keys = pff[["gameId", "playId"]].drop_duplicates()
print("pff plays not in plays.csv:",
      len(pff_keys.merge(plays[["gameId", "playId"]], how="left", indicator=True)
          .query("_merge=='left_only'")))
print("pff players not in players.csv:", (~pff["nflId"].isin(players["nflId"])).sum())

section("TRACKING (one game sample + all-game event coverage)")
files = sorted(glob.glob(f"{DATA}/tracking/*.csv"))
print("tracking files:", len(files), " games.csv:", len(games))
t = pd.read_csv(files[0])
print("sample rows:", len(t), " plays:", t["playId"].nunique())
print("dup (play, player, frame):", t.duplicated(["playId", "nflId", "frameId"]).sum())
print("ball rows (nflId NaN):", t["nflId"].isna().sum(), " team values:", t["team"].unique())
print("playDirection:", t["playDirection"].value_counts().to_dict())
print("frames per play: min/median/max",
      t.groupby("playId")["frameId"].max().describe()[["min", "50%", "max"]].to_dict())

# Event coverage across ALL games (read only the columns we need)
ev = pd.concat(
    pd.read_csv(f, usecols=["gameId", "playId", "event"]).query("event != 'None'")
    .drop_duplicates()
    for f in files
)
print("\nevent counts (play-level, all games):")
print(ev["event"].value_counts().to_string())
n_plays = len(plays)
for e in ["ball_snap", "pass_forward", "pass_arrived", "pass_outcome_caught"]:
    n = ev[ev["event"] == e][["gameId", "playId"]].drop_duplicates().shape[0]
    print(f"plays with {e}: {n} / {n_plays}")

section("TRACKING EXTENT: does it continue after the throw?")
last = t.groupby("playId")["event"].apply(lambda s: [x for x in s.unique() if x != "None"])
print(last.head(15).to_string())
