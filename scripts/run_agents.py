#!/usr/bin/env python3
"""
CLI for running AthFuelPath AI agents locally (voice meal, recipe selector).

Requires AWS credentials in .env or environment. Voice meal analysis also uses FDC_API_KEY.

Usage:
  python scripts/run_agents.py voice "grilled chicken and brown rice"
  python scripts/run_agents.py voice "eggs and toast" --allergies dairy
  python scripts/run_agents.py recipe halftime
  python scripts/run_agents.py recipe pre_game --allergies dairy,peanuts
  python scripts/run_agents.py demo
  python scripts/run_agents.py demo --mock
"""

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))


def _hr(char="─", width=60):
    return char * width


def _print_voice(result: dict):
    print(f"\n{_hr('═')}")
    print("  VOICE MEAL ANALYZER")
    print(_hr("═"))
    print(f'\n  Transcription: "{result["transcription"]}"')
    print(f'  Description:   {result["description"]}\n')
    print("  Detected foods:")
    for f in result["foods"]:
        print(f"    • {f['name']} (~{f['estimated_portion_g']}g)")
        print(
            f"      {f['calories']} kcal · P {f['protein_g']}g · "
            f"C {f['carbs_g']}g · F {f['fat_g']}g"
        )
        if f.get("fdc_description"):
            print(f"      USDA: {f['fdc_description']}")
    totals = result["totals"]
    print(f"\n  {_hr()}")
    print(
        f"  TOTAL  {totals['calories']} kcal · P {totals['protein_g']}g · "
        f"C {totals['carbs_g']}g · F {totals['fat_g']}g"
    )


def _print_recipe(result: dict):
    r = result["recipe"]
    print(f"\n{_hr('═')}")
    print("  RECIPE SELECTOR")
    print(_hr("═"))
    print(f"\n  {r['name']}")
    print(f"  Category: {r['category']}")
    print(
        f"  Macros: {r['calories']} kcal · P {r['protein_g']}g · "
        f"C {r['carbs_g']}g · F {r['fat_g']}g"
    )
    print(f"  Tags: {', '.join(r.get('tags', []))}\n")
    print("  Library ingredients:")
    for name in result.get("source_ingredients", []):
        print(f"    • {name}")
    print("\n  Recipe ingredients:")
    for item in r.get("ingredients", []):
        print(f"    • {item}")
    notes = r.get("preparation_notes", "")
    print(f"\n  Preparation:\n  {notes.replace(chr(10), chr(10) + '  ')}")


def _mock_voice(transcription: str) -> dict:
    return {
        "transcription": transcription,
        "description": "grilled chicken breast (~120g), brown rice (~150g)",
        "foods": [
            {
                "name": "grilled chicken breast",
                "estimated_portion_g": 120,
                "calories": 198,
                "protein_g": 37.2,
                "carbs_g": 0,
                "fat_g": 4.3,
                "fdc_id": 171077,
                "fdc_description": "Chicken, breast, grilled",
            },
            {
                "name": "brown rice",
                "estimated_portion_g": 150,
                "calories": 185,
                "protein_g": 4.1,
                "carbs_g": 38.4,
                "fat_g": 1.5,
                "fdc_id": 168878,
                "fdc_description": "Rice, brown, cooked",
            },
        ],
        "totals": {"calories": 383, "protein_g": 41.3, "carbs_g": 38.4, "fat_g": 5.8},
    }


def _mock_recipe(category: str) -> dict:
    return {
        "recipe": {
            "name": "Quick Halftime Banana Bites",
            "category": category,
            "calories": 220,
            "protein_g": 4,
            "carbs_g": 45,
            "fat_g": 2,
            "ingredients": ["1 medium banana", "2 tbsp honey"],
            "preparation_notes": "Slice banana. Drizzle honey. Eat within 5 minutes.",
            "tags": ["halftime", "quick", "carbs"],
        },
        "source_ingredients": ["Bananas, raw", "Honey"],
    }


def cmd_voice(args):
    from api.services import voice_meal_analyzer

    allergies = [a.strip() for a in (args.allergies or "").split(",") if a.strip()]
    if args.mock:
        result = _mock_voice(args.text)
    else:
        result = voice_meal_analyzer.analyze_voice(args.text, allergies=allergies or None)
    _print_voice(result)
    if args.json:
        print(json.dumps(result, indent=2))


def cmd_recipe(args):
    from api.services import recipe_generator

    allergies = [a.strip() for a in (args.allergies or "").split(",") if a.strip()]
    dietary = [d.strip() for d in (args.dietary or "").split(",") if d.strip()]
    if args.mock:
        result = _mock_recipe(args.category)
    else:
        result = recipe_generator.generate_recipe(
            args.category,
            allergies=allergies or None,
            dietary_restrictions=dietary or None,
        )
    _print_recipe(result)
    if args.json:
        print(json.dumps(result, indent=2))


def cmd_demo(args):
    meal = args.meal or "grilled chicken breast with brown rice and steamed broccoli"
    category = args.category or "halftime"
    print(_hr("═"))
    print("  AthFuelPath Agent Pipeline Demo")
    print(_hr("═"))
    print(f"  Mode:            {'MOCK (no API calls)' if args.mock else 'LIVE'}")
    print(f'  Meal transcript: "{meal}"')
    print(f"  Recipe category: {category}")

    from types import SimpleNamespace

    print("\n⏳ Running voice meal analyzer…")
    cmd_voice(SimpleNamespace(text=meal, allergies=args.allergies, mock=args.mock, json=False))
    print("\n⏳ Running recipe selector…")
    cmd_recipe(
        SimpleNamespace(
            category=category,
            allergies=args.allergies,
            dietary=args.dietary,
            mock=args.mock,
            json=False,
        )
    )
    print(f"\n{_hr('═')}")
    print("  DONE")
    print(_hr("═"))


def main():
    parser = argparse.ArgumentParser(description="Run AthFuelPath AI agents locally")
    sub = parser.add_subparsers(dest="command", required=True)

    voice = sub.add_parser("voice", help="Analyze a meal description (voice/text)")
    voice.add_argument("text", help="Meal description transcript")
    voice.add_argument("--allergies", help="Comma-separated allergens to avoid")
    voice.add_argument("--mock", action="store_true", help="Print mock output (no API keys)")
    voice.add_argument("--json", action="store_true", help="Also print raw JSON")

    recipe = sub.add_parser("recipe", help="Select a recipe from the library for a category")
    recipe.add_argument("category", help="Recipe category (e.g. halftime, pre_game)")
    recipe.add_argument("--allergies", help="Comma-separated allergens to avoid")
    recipe.add_argument("--dietary", help="Comma-separated dietary restrictions")
    recipe.add_argument("--mock", action="store_true", help="Print mock output (no API keys)")
    recipe.add_argument("--json", action="store_true", help="Also print raw JSON")

    demo = sub.add_parser("demo", help="Run voice + recipe pipeline")
    demo.add_argument("meal", nargs="?", help="Meal transcript for voice agent")
    demo.add_argument("category", nargs="?", help="Recipe category")
    demo.add_argument("--allergies", help="Comma-separated allergens to avoid")
    demo.add_argument("--dietary", help="Comma-separated dietary restrictions")
    demo.add_argument("--mock", action="store_true", help="Print mock output (no API keys)")

    args = parser.parse_args()
    try:
        if args.command == "voice":
            cmd_voice(args)
        elif args.command == "recipe":
            cmd_recipe(args)
        else:
            cmd_demo(args)
    except (ValueError, RuntimeError) as e:
        print(f"\n✗ Failed: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
