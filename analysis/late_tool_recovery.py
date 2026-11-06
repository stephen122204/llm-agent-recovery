"""Recompute the main study's warm-cache, late tool-error comparison (Table 1)."""
import csv
from pathlib import Path

GOALS = Path(__file__).resolve().parents[1] / "data/dataset/goals.csv"


def main():
    with GOALS.open(newline="") as stream:
        goals = [
            row for row in csv.DictReader(stream)
            if row["study"] in {"e1", "e1b"} and row["arm"] == "fixed"
            and row["class"] == "tool_error" and row["position"] == "late"
        ]
    print("Recovery              Correct     Mean J/run    J/successful goal")
    for option in ("FR_warm", "SR_warm", "SG_warm", "RB_warm"):
        runs = [row for row in goals if row["option"] == option]
        energy = sum(float(row["board_j"]) for row in runs)
        successes = sum(int(row["outcome"]) for row in runs)
        print(f"{option:20}  {successes:2}/{len(runs):2}     {energy / len(runs):10,.0f}    {energy / successes:17,.0f}")


if __name__ == "__main__":
    main()
