"""
AI NETRA — Height Data Diagnostics
Workstream: GEO-001
Step: 8.28

Investigates missing and invalid height values.

Read-only diagnostic.
Does not modify source files.
"""

import csv
import math
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"

FILES = [
    DATA / "ai_netra_building_heights_2023_v1.csv",
    DATA / "ai_netra_expanded_heights_2023_v1.csv",
]

print("\nAI NETRA — HEIGHT DATA DIAGNOSTICS")
print("=" * 55)

for file_path in FILES:

    print(f"\nSOURCE: {file_path.name}")
    print("-" * 55)

    total = 0
    valid = 0
    missing = 0
    invalid = 0
    low = 0

    invalid_samples = []
    missing_samples = []

    reasons = Counter()

    with open(
        file_path,
        newline="",
        encoding="utf-8-sig"
    ) as file:

        reader = csv.DictReader(file)

        print("CSV Columns:", reader.fieldnames)

        for row in reader:

            total += 1

            building_id = row.get(
                "building_id", ""
            )

            raw_height = row.get(
                "estimated_height_m"
            )

            if raw_height is None or not raw_height.strip():

                missing += 1
                reasons["empty_height"] += 1

                if len(missing_samples) < 5:
                    missing_samples.append({
                        "building_id": building_id,
                        "raw_height": raw_height
                    })

                continue

            try:

                height = float(raw_height)

                if not math.isfinite(height):
                    raise ValueError("Non-finite height")

                if height <= 0:
                    invalid += 1
                    reasons["non_positive"] += 1

                    if len(invalid_samples) < 5:
                        invalid_samples.append({
                            "building_id": building_id,
                            "raw_height": raw_height
                        })

                    continue

                valid += 1

                if height < 2:
                    low += 1

            except ValueError:

                invalid += 1
                reasons["not_numeric"] += 1

                if len(invalid_samples) < 5:
                    invalid_samples.append({
                        "building_id": building_id,
                        "raw_height": raw_height
                    })

    print(f"Total records: {total}")
    print(f"Valid heights: {valid}")
    print(f"Missing heights: {missing}")
    print(f"Invalid heights: {invalid}")
    print(f"Low heights (<2 m): {low}")

    print("\nFailure reasons:")

    for reason, count in reasons.items():
        print(f"  {reason}: {count}")

    if missing_samples:
        print("\nMissing value samples:")
        for sample in missing_samples:
            print(sample)

    if invalid_samples:
        print("\nInvalid value samples:")
        for sample in invalid_samples:
            print(sample)

print("\nDIAGNOSTICS COMPLETED")