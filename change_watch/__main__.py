"""Command-line entry point for reproducible image comparisons."""

import argparse
import json
from pathlib import Path

from . import __version__
from .analysis import analyze_pair
from .demo import synthetic_pair
from .export import build_artifacts, zip_artifacts
from .io import load_image


def read_rgb(path):
    return load_image(path)


def read_mask(path):
    return load_image(path, mask=True)


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="Compare aligned RGB images for candidate visual changes."
    )
    parser.add_argument("--version", action="version", version=f"Steppe Watch {__version__}")
    parser.add_argument(
        "--demo", action="store_true", help="Use synthetic images, not satellite observations."
    )
    parser.add_argument("--before", type=Path)
    parser.add_argument("--after", type=Path)
    parser.add_argument(
        "--valid-mask", type=Path, help="White = usable in BOTH dates; black = excluded."
    )
    parser.add_argument(
        "--truth", type=Path, help="Reference mask: white = changed, black = unchanged."
    )
    parser.add_argument(
        "--evaluation-mask",
        type=Path,
        help="White = annotated pixels to evaluate; requires --truth. Does not restrict detection.",
    )
    parser.add_argument("--threshold", type=float, default=35)
    parser.add_argument("--min-pixels", type=int, default=25)
    parser.add_argument("--connectivity", type=int, choices=[4, 8], default=4)
    parser.add_argument("--correction", choices=["none", "median_offset"], default="none")
    parser.add_argument(
        "--metadata", type=Path, help="JSON object: site, before_date, after_date, source, notes."
    )
    parser.add_argument(
        "--acquisition", type=Path, help="Exported satellite_provenance.json for an offline replay."
    )
    parser.add_argument(
        "--sensitivity",
        action="store_true",
        help="Compare nearby thresholds without selecting one.",
    )
    parser.add_argument(
        "--zip", action="store_true", help="Also write experiment.zip containing all artifacts."
    )
    parser.add_argument(
        "--out",
        type=Path,
        default=Path("outputs/comparison"),
        help="A new or empty output directory.",
    )
    args = parser.parse_args(argv)
    if args.demo and any(
        [args.before, args.after, args.valid_mask, args.truth, args.evaluation_mask]
    ):
        parser.error("Use --demo on its own, or supply your own image paths and masks.")
    if not args.demo and (args.before is None or args.after is None):
        parser.error("Supply --demo or both --before and --after.")
    if args.evaluation_mask and not args.truth:
        parser.error("--evaluation-mask requires --truth.")
    try:
        if args.out.exists() and (not args.out.is_dir() or any(args.out.iterdir())):
            raise ValueError(
                "Output directory must be new or empty. Choose another --out to preserve previous runs."
            )
        metadata = (
            json.loads(args.metadata.read_text(encoding="utf-8-sig")) if args.metadata else None
        )
        if args.demo:
            before, after, truth = synthetic_pair()
            valid = None
            evaluation_mask = None
        else:
            before, after = read_rgb(args.before), read_rgb(args.after)
            truth = read_mask(args.truth) if args.truth else None
            valid = read_mask(args.valid_mask) if args.valid_mask else None
            evaluation_mask = read_mask(args.evaluation_mask) if args.evaluation_mask else None
        analysis = analyze_pair(
            before,
            after,
            threshold=args.threshold,
            min_pixels=args.min_pixels,
            valid_mask=valid,
            truth=truth,
            evaluation_mask=evaluation_mask,
            connectivity=args.connectivity,
            correction=args.correction,
            synthetic=args.demo,
            metadata=metadata,
            sensitivity=args.sensitivity,
            acquisition=(
                json.loads(args.acquisition.read_text(encoding="utf-8-sig"))
                if args.acquisition
                else None
            ),
        )
        artifacts = build_artifacts(analysis, before, after, truth)
        if args.zip:
            artifacts["experiment.zip"] = zip_artifacts(artifacts)
        args.out.mkdir(parents=True, exist_ok=True)
        for name, content in artifacts.items():
            (args.out / name).write_bytes(content)
        print(json.dumps(analysis.report, indent=2, allow_nan=False))
        print(f"Results saved to {args.out.resolve()}")
    except (OSError, ValueError) as error:
        parser.error(str(error))


if __name__ == "__main__":
    main()
