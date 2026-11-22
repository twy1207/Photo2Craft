"""One small offline build path. Photo analysis is added separately."""
import argparse
import json
from pathlib import Path

from .compile import compile_plan
from .model import Plan
from .render import write_comparison


def save_json(path: Path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def build(plan_path: Path, out: Path, photo: Path | None, extent: int):
    plan = Plan.model_validate_json(plan_path.read_text(encoding="utf-8"))
    result = compile_plan(plan, extent)
    out.mkdir(parents=True, exist_ok=True)
    save_json(out / "blocks.json", result.as_dict())
    save_json(out / "summary.json", {
        "block_count": len(result.blocks),
        "size": [max(p[i] for p in result.blocks)+1 for i in range(3)],
        "warnings": result.warnings,
        "note": "Structural diagnostics, not photo similarity scores.",
    })
    write_comparison(result, photo, out / "comparison.png")
    print(f"Built {len(result.blocks)} blocks; {len(result.warnings)} warnings. Output: {out}")


def main():
    parser = argparse.ArgumentParser(description="Photo2Craft generation experiment")
    sub = parser.add_subparsers(dest="command", required=True)
    b = sub.add_parser("build", help="compile a saved plan without an API key")
    b.add_argument("plan", type=Path)
    b.add_argument("--photo", type=Path)
    b.add_argument("--out", type=Path, required=True)
    b.add_argument("--extent", type=int, default=48)
    args = parser.parse_args()
    try:
        build(args.plan, args.out, args.photo, args.extent)
    except (ValueError, OSError) as exc:
        parser.exit(1, f"{type(exc).__name__}: {exc}\n")


if __name__ == "__main__":
    main()
