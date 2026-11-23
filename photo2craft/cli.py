"""Photo analysis and an offline build path, without a web application."""
import argparse
import hashlib
import importlib.metadata
import json
from pathlib import Path

from .model import parse_plan_json
from .pipeline import compile_document
from .render import write_comparison


def save_json(path: Path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n")


def build(plan_path: Path, out: Path, photo: Path | None, extent: int):
    original = parse_plan_json(plan_path.read_text(encoding="utf-8"))
    plan, result, resolution = compile_document(original, extent)
    out.mkdir(parents=True, exist_ok=True)
    if resolution is not None:
        save_json(out / 'resolved-plan.json', plan.model_dump(mode='json'))
        save_json(out / 'spatial-resolution.json', resolution)
    save_json(out / "blocks.json", result.as_dict())
    save_json(out / "summary.json", {
        "block_count": len(result.blocks),
        "size": [max(p[i] for p in result.blocks)+1 for i in range(3)],
        "warnings": result.warnings,
        "note": "Structural diagnostics, not photo similarity scores.",
    })
    write_comparison(result, photo, out / "comparison.png", plan.view)
    save_json(out / "build.json", {
        "extent": extent,
        "plan_sha256": hashlib.sha256(plan_path.read_bytes()).hexdigest(),
        "photo_sha256": hashlib.sha256(photo.read_bytes()).hexdigest() if photo else None,
        "source_sha256": {name: hashlib.sha256(Path(__file__).with_name(name).read_bytes()).hexdigest()
                          for name in ("model.py", "compile.py", "pipeline.py", "render.py") + (("spatial.py",) if resolution is not None else ())},
        "dependencies": {name: importlib.metadata.version(name) for name in ("Pillow", "pydantic")},
    })
    print(f"Built {len(result.blocks)} blocks; {len(result.warnings)} warnings. Output: {out}")


def main():
    parser = argparse.ArgumentParser(description="Photo2Craft generation experiment")
    sub = parser.add_subparsers(dest="command", required=True)
    b = sub.add_parser("build", help="compile a saved plan without an API key")
    b.add_argument("plan", type=Path)
    b.add_argument("--photo", type=Path)
    b.add_argument("--out", type=Path, required=True)
    b.add_argument("--extent", type=int, default=48)
    a = sub.add_parser("analyze", help="send one photo to Gemini, then compile the returned plan")
    a.add_argument("photo", type=Path)
    a.add_argument("--out", type=Path, required=True)
    a.add_argument("--model", default="gemini-3.5-flash-lite")
    a.add_argument("--requirements", default="")
    a.add_argument("--extent", type=int, default=48)
    t = sub.add_parser('attach', help='experimental additions to an immutable v1 plan')
    t.add_argument('baseline', type=Path)
    t.add_argument('--photo', type=Path, required=True)
    t.add_argument('--out', type=Path, required=True)
    t.add_argument('--model', default='gemini-3.5-flash-lite')
    t.add_argument('--extent', type=int, default=48)
    r = sub.add_parser("replay", help="validate a saved API response and build it without another API call")
    r.add_argument("response", type=Path)
    r.add_argument("--photo", type=Path)
    r.add_argument("--out", type=Path, required=True)
    r.add_argument("--extent", type=int, default=48)
    r.add_argument('--baseline', type=Path, help='v1 baseline for replaying an attachment proposal response')
    s = sub.add_parser('serve', help='open the local 3D example viewer without an API key')
    s.add_argument('--port', type=int, default=8000)
    s.add_argument('--examples', type=Path, default=Path('examples'))
    args = parser.parse_args()
    try:
        if args.command == 'serve':
            from .server import serve
            serve(args.examples, args.port)
        elif args.command == 'analyze':
            from .analyze import analyze
            plan = analyze(args.photo, args.out, args.model, args.requirements)
            build(plan, args.out, args.out/'input.jpg', args.extent)
        elif args.command == 'attach':
            from .analyze import analyze
            plan = analyze(args.photo, args.out, args.model, '', base_plan=args.baseline)
            build(plan, args.out, args.out/'input.jpg', args.extent)
        elif args.command == 'replay':
            from .analyze import read_plan
            if args.out.exists():
                raise ValueError('replay output directory already exists; choose a new directory')
            raw = args.response.read_bytes()
            if args.baseline is not None:
                from .model import Plan
                from .spatial import AttachmentProposal, OverlayPlan
                baseline = Plan.model_validate_json(args.baseline.read_text(encoding='utf-8'))
                proposal = read_plan(json.loads(raw), AttachmentProposal)
                plan = OverlayPlan(schema_version=3, baseline=baseline, additions=proposal)
                plan.spatial_plan()
            else:
                plan = read_plan(json.loads(raw))
            args.out.mkdir(parents=True)
            save_json(args.out/'plan.json', plan.model_dump(mode='json'))
            save_json(args.out/'replay.json', {
                'response_sha256': hashlib.sha256(raw).hexdigest(),
                'baseline_sha256': hashlib.sha256(args.baseline.read_bytes()).hexdigest() if args.baseline else None,
                'note': 'Unedited model response validated by the current parser; no API request or hand-edited plan.',
            })
            build(args.out/'plan.json', args.out, args.photo, args.extent)
        else:
            build(args.plan, args.out, args.photo, args.extent)
    except (ValueError, OSError) as exc:
        parser.exit(1, f"{type(exc).__name__}: {exc}\n")


if __name__ == "__main__":
    main()
