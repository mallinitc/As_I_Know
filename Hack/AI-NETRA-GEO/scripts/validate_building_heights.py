import csv
import statistics
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent

CSV_FILE = (
    PROJECT_ROOT
    / "data"
    / "ai_netra_building_heights_2023_v1.csv"
)

records = []
heights = []
missing = []
suspicious = []
building_ids = set()
duplicates = []

with open(CSV_FILE, newline="", encoding="utf-8-sig") as file:
    reader = csv.DictReader(file)

    for row in reader:
        records.append(row)

        building_id = row.get("building_id", "")

        if building_id in building_ids:
            duplicates.append(building_id)

        building_ids.add(building_id)

        raw_height = row.get("estimated_height_m", "")

        if not raw_height:
            missing.append(building_id)
            continue

        try:
            height = float(raw_height)
        except ValueError:
            missing.append(building_id)
            continue

        heights.append(height)

        # Screening thresholds only, not proof of invalid data.
        if height <= 0 or height > 100:
            suspicious.append((building_id, height))

print("\nAI NETRA — BUILDING HEIGHT VALIDATION")
print("=" * 45)

print(f"Total records: {len(records)}")
print(f"Unique building IDs: {len(building_ids)}")
print(f"Valid numeric heights: {len(heights)}")
print(f"Missing/invalid heights: {len(missing)}")
print(f"Duplicate IDs: {len(duplicates)}")
print(f"Flagged heights: {len(suspicious)}")

if heights:
    print("\nHEIGHT STATISTICS")
    print(f"Minimum: {min(heights):.2f} m")
    print(f"Maximum: {max(heights):.2f} m")
    print(f"Average: {statistics.mean(heights):.2f} m")
    print(f"Median: {statistics.median(heights):.2f} m")

print("\nSAMPLE BUILDINGS")

for row in records[:10]:
    print(
        row.get("building_id"),
        "=>",
        row.get("estimated_height_m"),
        "metres"
    )

if suspicious:
    print("\nFLAGGED HEIGHTS")
    for building_id, height in suspicious:
        print(building_id, height)