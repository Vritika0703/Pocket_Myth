# Man-Beater Score: who gets open against man coverage, and do QBs notice?

We built the **Man-Beater Score**, a new metric for WRs, TEs and RBs: a player's separation from the nearest defender at the moment of the throw, against man coverage, minus what a typical player at his position gets in that coverage with the same time to throw (2021 Weeks 1–8 tracking, 30,288 routes, 74 players with ≥40 routes vs man). Separation clearly pays off, since WR/TE completion rate climbs from 25% under 1 yard of separation to 74% at 3–4 yards, yet QBs don't consistently feed the players who create it: Kalif Raymond, Cole Beasley, Adam Humphries and Ezekiel Elliott beat man coverage but are targeted only 12–14% of the time, while Travis Kelce, Kyle Pitts and Ja'Marr Chase get the least separation and are still targeted 30–38% of the time. Coaches can use the "Open but Ignored" list to call plays against man, and scouts can use the score to find route runners whose production undersells them. Method: positions come from the tracking frame of the first `pass_forward` event, defenders are players with PFF role `Coverage`, the targeted receiver is parsed from `playDescription` (the 7% of throws we couldn't match were dropped), and expected separation is a linear fit on time-to-throw within each position × coverage group. Limitations: tracking ends ~0.5 s after the throw so we can't measure separation at the catch, samples are small (40–70 man routes per player, wide confidence intervals, split-half reliability r = 0.27) so treat the score as a scouting flag rather than a verdict, and target rate isn't adjusted for position or for the other options on the play.

## Results

**1. Separation pays off, especially against man**
![Separation payoff](output/separation_payoff.png)

**2. Man-Beater leaderboard (±95% CI)**
![Leaderboard](output/man_beater_leaderboard.png)

**3. Open vs Fed: who beats man coverage but doesn't get the ball**
![Open vs Fed](output/open_vs_fed.png)

All scores: [`output/man_beater_scores.csv`](output/man_beater_scores.csv) · per-route data: [`output/route_separation.csv`](output/route_separation.csv)

## Bonus: Receiver-Line Fit: is a late-opening receiver wasted behind a weak line?

**Question:** some receivers get open early (quick routes) and some get open late (deeper routes); some teams' pass protection holds up long and some collapses fast. Which receivers suit which team's line? For each team we measured **how long the pocket stays intact** (first frame a pass rusher is within 2 yards of the QB, using a Kaplan-Meier curve so plays that end in a throw before any collapse still count). For each receiver we measured **when he first gets open** on every route (≥3 yards from every coverage defender, ≥3 yards past the line, ≥0.5 s after the snap). **Fit Score** = share of his routes on which he gets open while that team's pocket would still be intact; **in-time rate** = the same, counting only routes where he does get open.

**Findings:**
- **Late openers are hurt most by a weak line.** Moving from the 5 best pass-blocking lines (BAL, TB, CLE, ARI, LA) to the 5 worst (MIN, LAC, DEN, NE, MIA) drops the in-time rate by **5.3 points for early openers (~1.4 s)** but **7.1 points for late openers (~1.8 s)**. Across all 99 players, open time and this loss correlate at r = 0.86.
- **Most at risk:** pass-catching TEs (Tyler Conklin −10.1, Noah Fant −9.8, Jared Cook −9.5, Zach Ertz −9.4) and receiving RBs (Austin Ekeler, J.D. McKissic, D'Andre Swift, about 65–80% in time behind weak lines).
- **But the receiver still matters most:** team averages differ by only ~5 points, while players' Fit Scores range from 5% to 76%. A coach adding a quick-opening WR doesn't need to worry much about the line; a coach adding a late-opening TE or RB should.

**Who uses it:** a GM or coach weighing a receiver for their roster (look up his best and worst team fits in [`output/fit_best_teams.csv`](output/fit_best_teams.csv)).
**Limitations:** the effect grows with open time partly by construction (later moments always have fewer pockets intact), so the contribution here is measuring *how big* it is; "open" uses fixed distance thresholds; open time also reflects route design; a new team's QB and play-calling would change things; 8 weeks of data.

![Fit timing](output/fit_timing.png)

![Fit heatmap](output/fit_heatmap.png)

Fit scores for 99 players × 32 teams: [`output/fit_scores.csv`](output/fit_scores.csv)

## Reproduce (about 15 seconds)

```bash
git clone --depth 1 https://github.com/ThompsonJamesBliss/nfl-big-data-bowl-regional-event-data.git data-src
pip install -r requirements.txt
python src/build_features.py   # -> output/route_separation.csv
python src/man_beater.py       # -> scores CSV + 3 charts
python src/fit_score.py        # -> fit scores + heatmap (bonus)
python src/fit_deep.py         # -> early vs late openers chart + best-fit teams
```

`src/explore.py` and `src/traps.py` are the data checks we ran first: join keys, coverage labels, duplicate snap/throw events, where tracking ends, and target parsing.
