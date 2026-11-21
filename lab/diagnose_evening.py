"""Investigate the existing evening model without modifying its owner files.

Control one dimension at a time: 5 temperatures x 3 initial fuels x 4
nightly recovery rates. Three announced plans per identical starting state.
"""
from __future__ import annotations

import argparse
import json
from .evening import COOLING_RATE_C_PER_H
from .evening_run import plans

TEMPERATURES = (-24, -18, -12, -6, -2)
FUELS = (3, 5, 7)
RECOVERIES = (2.0, 4.0, 6.0, 8.0)


def diagnose() -> dict:
    cells = []
    for recovery in RECOVERIES:
        for temp in TEMPERATURES:
            for fuel in FUELS:
                result = plans(temp, COOLING_RATE_C_PER_H, fuel, recovery)
                considered = result["plans"][0]["considered"]
                warm_options = sum(not x["expects_to_wake_cold"] for x in considered)
                choices = [x["chose"][0] for x in result["plans"]]
                cells.append({
                    "recovery_h": recovery, "temp_c": temp, "fuel": fuel,
                    "warm_options": warm_options,
                    "distinct_evening_choices": len(set(choices)),
                    "choices": choices,
                    "plan_refusals": sum(not x["could_leave_in_the_morning"] for x in result["plans"]),
                    "morning_fatigue": [x["morning_fatigue"] for x in result["plans"]],
                })
    summaries = []
    for rec in RECOVERIES:
        group = [x for x in cells if x["recovery_h"] == rec]
        summaries.append({
            "recovery_h": rec,
            "cells": len(group),
            "plans_change_evening": sum(x["distinct_evening_choices"] > 1 for x in group),
            "cells_with_two_warm_options": sum(x["warm_options"] >= 2 for x in group),
            "plan_refusals": sum(x["plan_refusals"] for x in group),
        })
    return {
        "method": "Paired counterfactual plans; only recovery varies between grids.",
        "summary_by_recovery": summaries,
        "cells": cells,
        "changed_cells": [x for x in cells if x["distinct_evening_choices"] > 1],
        "limits": [
            "Checks the actual evening code currently in production, not the Codex branch.",
            "Warm-option selection and recovery can both suppress plan influence.",
            "No player outcomes or game-engine runtime measured.",
        ],
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--json")
    parser.add_argument("--brief", action="store_true")
    args = parser.parse_args()
    result = diagnose()
    if args.json:
        with open(args.json, "w", encoding="utf-8") as file:
            json.dump(result, file, ensure_ascii=False, indent=2)
    if args.brief:
        result.pop("cells")
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
