# Is this receiver good, and would he fit our quarterback?

We built a tool that answers one question about NFL receivers: is he good at getting open, and would he fit a given team's quarterback? Using 2021 tracking data, it scores each WR and TE against man and zone coverage, then estimates how often he'd be open before each team's QB throws. Pittsburgh's quick release is the worst fit for every receiver, and tight ends depend on the quarterback the most. When seven teams changed quarterbacks mid-season, our predictions matched how 28 receivers' numbers actually changed (r = 0.52, rising to 0.93 for players with larger samples). Scouts and GMs can use it to judge a receiver and his fit; it predicts timing, not target share, and is based on 8 weeks of data.

![Would he fit this QB?](output/qb_fit.png)

![Validated on mid-season QB changes](output/qb_change_validation.png)

![Is he good, and against which coverage?](output/profile_man_zone.png)

**Run it:** `pip install -r requirements.txt`, clone the [dataset](https://github.com/ThompsonJamesBliss/nfl-big-data-bowl-regional-event-data) into `data-src/`, then run the scripts in `src/` in the order listed in [METHODS.md](METHODS.md#reproduce-about-2-minutes).
**Full method, definitions and extra results:** [METHODS.md](METHODS.md).
