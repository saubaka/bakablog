"""Check the blue outline's top-center seam in stable QA screenshots.

Run after the normal-motion screenshot fixture, not on arbitrary user themes:
python scripts/check_outline_pixels.py session-data/qa/<run>/phase2-final-checks.json
The 25-column pixel check complements, but never replaces, geometry and visual QA.
"""
import argparse
import json
from pathlib import Path

from PIL import Image


def inspect(report: Path) -> list[dict]:
    results = []
    for state in json.loads(report.read_text(encoding="utf-8"))["states"]:
        if state["page"] != "setup":
            continue
        card = next(item for item in state["geometry"] if "auth-card" in item["class"] or "setup-card" in item["class"])
        image_path = report.parent / f"{state['viewport']}-setup-final.png"
        with Image.open(image_path) as source:
            image = source.convert("RGB")
        x, y = round(card["center"]), round(card["top"])
        missing = []
        for dx in range(-12, 13):
            pixels = [image.getpixel((x + dx, y + dy)) for dy in range(-1, 4)]
            if not any(blue - red > 13 and green - red > 6 and red < 232
                       for red, green, blue in pixels):
                missing.append(dx)
        results.append({"viewport": state["viewport"], "checked_columns": 25,
                        "missing_columns": missing, "image": image_path.name})
    if len(results) != 3 or any(item["missing_columns"] for item in results):
        raise AssertionError(f"Incomplete top-center outline: {results}")
    return results


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("report", type=Path)
    args = parser.parse_args()
    print(json.dumps(inspect(args.report), ensure_ascii=False, indent=2))
