"""Sensitivity of the Receiver-Line Fit results to the two distance thresholds.

Re-runs fit_score.py's pipeline for several (open distance, pocket-collapse distance) settings and
reports the model's early-vs-late loss and the reality-check gap for each.
Output: output/fit_sensitivity.csv
"""
import os
import sys

import pandas as pd

sys.path.insert(0, os.path.dirname(__file__))
import fit_deep as fd  # noqa: E402
import fit_score as fs  # noqa: E402

CONFIGS = [(3.0, 2.0), (2.5, 2.0), (3.5, 2.0), (3.0, 1.5), (3.0, 2.5)]
rows = []
for open_yd, rush_yd in CONFIGS:
    tag = f"_o{open_yd}_r{rush_yd}"
    pockets, routes = fs.extract(open_yd, rush_yd)
    S, fit = fs.fit_scores(pockets, routes)
    routes.to_csv(f"{fs.OUT}/fit_routes{tag}.csv", index=False)
    S.to_csv(f"{fs.OUT}/fit_pocket_curves{tag}.csv")
    fit.to_csv(f"{fs.OUT}/fit_scores{tag}.csv", index=False)
    _, _, line, _, wt, _, res = fd.summarize(tag, verbose=False)
    rc = fd.reality_check(tag, wt, line, n_boot=200)["in_time"]
    rows.append({"open_yd": open_yd, "collapse_yd": rush_yd,
                 "model_loss_early": round(res["early_loss"], 1), "model_loss_late": round(res["late_loss"], 1),
                 "model_corr": round(res["corr"], 2),
                 "reality_gap": round(rc["did"], 1), "reality_lo": round(rc["lo"], 1), "reality_hi": round(rc["hi"], 1)})
    for f in ["fit_routes", "fit_pocket_curves", "fit_scores"]:
        os.remove(f"{fs.OUT}/{f}{tag}.csv")
out = pd.DataFrame(rows)
out.to_csv(f"{fs.OUT}/fit_sensitivity.csv", index=False)
print(out.to_string(index=False))
