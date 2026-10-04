import argparse
import json
from pathlib import Path

import numpy as np
from PIL import Image, ImageOps

from .core import detect_changes, evaluate_mask, make_overlay
from .demo import synthetic_pair


def read_rgb(path):
    with Image.open(path) as image:
        return np.array(ImageOps.exif_transpose(image).convert("RGB"))


def read_mask(path):
    with Image.open(path) as image:
        return np.array(ImageOps.exif_transpose(image).convert("L")) > 127


def main():
    parser = argparse.ArgumentParser(description="Compare aligned RGB images for candidate visual changes.")
    parser.add_argument("--demo", action="store_true", help="Use generated synthetic images, not satellite observations.")
    parser.add_argument("--before", type=Path)
    parser.add_argument("--after", type=Path)
    parser.add_argument("--valid-mask", type=Path, help="White = usable in BOTH dates; black = excluded.")
    parser.add_argument("--truth", type=Path, help="Optional reference change mask, white = changed.")
    parser.add_argument("--threshold", type=float, default=35)
    parser.add_argument("--min-pixels", type=int, default=25)
    parser.add_argument("--out", type=Path, default=Path("outputs"))
    args = parser.parse_args()
    if args.demo and any([args.before, args.after, args.valid_mask, args.truth]):
        parser.error("Use --demo on its own, or supply your own image paths and masks.")
    if not args.demo and (args.before is None or args.after is None):
        parser.error("Supply --demo or both --before and --after.")
    try:
        if args.demo:
            before, after, truth = synthetic_pair()
            valid = None
        else:
            before, after = read_rgb(args.before), read_rgb(args.after)
            truth = read_mask(args.truth) if args.truth else None
            valid = read_mask(args.valid_mask) if args.valid_mask else None
        result = detect_changes(before, after, args.threshold, args.min_pixels, valid)
        report = dict(result.summary)
        report["data_source"] = "synthetic_demo" if args.demo else "user_supplied_rgb_images"
        if truth is not None:
            report["evaluation"] = evaluate_mask(result.mask, truth, result.valid)
            report["evaluation_scope"] = "Synthetic pipeline check only; not evidence of real-world accuracy." if args.demo else "User-provided reference mask; quality and coverage are not verified."
        args.out.mkdir(parents=True, exist_ok=True)
        Image.fromarray(make_overlay(after, result.mask)).save(args.out / "overlay.png")
        Image.fromarray(result.mask.astype(np.uint8) * 255).save(args.out / "change_mask.png")
        Image.fromarray(result.score.astype(np.uint8)).save(args.out / "difference.png")
        (args.out / "report.json").write_text(json.dumps(report, indent=2) + "\n")
        print(json.dumps(report, indent=2))
        print(f"Results saved to {args.out.resolve()}")
    except (OSError, ValueError) as error:
        parser.error(str(error))


if __name__ == "__main__":
    main()
