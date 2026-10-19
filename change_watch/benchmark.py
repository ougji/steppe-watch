"""Evaluate fixed detector settings across annotated image pairs."""

import argparse
import csv
import hashlib
import io
import json
import re
from datetime import datetime, timezone
from pathlib import Path

from . import __version__
from .analysis import analyze_pair, validate_metadata
from .io import load_image

METRICS = ("precision", "recall", "f1", "iou")
COUNTS = (
    "true_positive_pixels",
    "false_positive_pixels",
    "false_negative_pixels",
    "true_negative_pixels",
)
REQUIRED_PATHS = {"before", "after", "truth"}
OPTIONAL_PATHS = {"valid_mask", "evaluation_mask"}


def read_manifest(path):
    """Read a strict manifest; relative image paths belong to its directory."""
    manifest = json.loads(Path(path).read_text(encoding="utf-8-sig"))
    if not isinstance(manifest, dict) or set(manifest) - {"schema_version", "synthetic", "cases"}:
        raise ValueError(
            "Benchmark manifest must contain schema_version, synthetic and cases only."
        )
    if manifest.get("schema_version") != "1.0":
        raise ValueError("Benchmark manifest schema_version must be '1.0'.")
    if not isinstance(manifest.get("synthetic", False), bool):
        raise ValueError("Manifest synthetic must be true or false.")
    cases = manifest.get("cases")
    if not isinstance(cases, list) or not cases:
        raise ValueError("Benchmark needs a nonempty cases list.")
    identifiers = set()
    for case in cases:
        allowed = {"id", "metadata"} | REQUIRED_PATHS | OPTIONAL_PATHS
        if not isinstance(case, dict) or set(case) - allowed:
            raise ValueError(
                "Each case must contain an id, image/mask paths and optional metadata."
            )
        identifier = case.get("id")
        if not isinstance(identifier, str) or not re.fullmatch(
            r"[A-Za-z0-9][A-Za-z0-9_-]{0,63}", identifier
        ):
            raise ValueError("Case IDs must be 1–64 letters, digits, underscores or hyphens.")
        if identifier in identifiers:
            raise ValueError(f"Duplicate case ID: {identifier}.")
        identifiers.add(identifier)
        if not REQUIRED_PATHS <= set(case):
            raise ValueError(f"Case '{identifier}' requires before, after and truth paths.")
        for key in (REQUIRED_PATHS | OPTIONAL_PATHS) & set(case):
            if not isinstance(case[key], str) or not case[key].strip():
                raise ValueError(f"Case '{identifier}' needs a nonempty {key} path.")
        validate_metadata(case.get("metadata"))
    return manifest


def summarize(evaluations):
    """Pool confusion counts; average only defined per-pair metric values."""
    counts = {key: sum(evaluation[key] for evaluation in evaluations) for key in COUNTS}
    tp, fp, fn = (counts[key] for key in COUNTS[:3])
    ratios = {
        "precision": (tp, tp + fp),
        "recall": (tp, tp + fn),
        "f1": (2 * tp, 2 * tp + fp + fn),
        "iou": (tp, tp + fp + fn),
    }
    micro = {**counts, **{key: n / d if d else None for key, (n, d) in ratios.items()}}
    values = {key: [row[key] for row in evaluations if row[key] is not None] for key in METRICS}
    return {
        "micro": micro,
        "macro": {key: sum(items) / len(items) if items else None for key, items in values.items()},
        "macro_defined_cases": {key: len(items) for key, items in values.items()},
    }


def run_benchmark(
    manifest_path,
    *,
    threshold=35.0,
    min_pixels=25,
    connectivity=4,
    corrections=("none", "median_offset"),
):
    """Run every case under the same settings; never select or tune a winner."""
    if isinstance(corrections, str):
        raise ValueError("Corrections must be a sequence of detector correction names.")
    corrections = list(corrections)
    if not corrections or any(value not in ("none", "median_offset") for value in corrections):
        raise ValueError("Choose at least one correction: none or median_offset.")
    if len(set(corrections)) != len(corrections):
        raise ValueError("Corrections must be unique.")
    manifest_path = Path(manifest_path)
    manifest = read_manifest(manifest_path)
    synthetic = manifest.get("synthetic", False)
    results = []
    for case in manifest["cases"]:
        try:
            images = {
                key: load_image(
                    manifest_path.parent / case[key], mask=key not in {"before", "after"}
                )
                for key in (REQUIRED_PATHS | OPTIONAL_PATHS) & set(case)
            }
            for correction in corrections:
                analysis = analyze_pair(
                    images["before"],
                    images["after"],
                    truth=images["truth"],
                    valid_mask=images.get("valid_mask"),
                    evaluation_mask=images.get("evaluation_mask"),
                    threshold=threshold,
                    min_pixels=min_pixels,
                    connectivity=connectivity,
                    correction=correction,
                    metadata=case.get("metadata"),
                    synthetic=synthetic,
                )
                results.append(
                    {"case_id": case["id"], "correction": correction, "report": analysis.report}
                )
        except (OSError, ValueError) as error:
            raise ValueError(f"Case '{case['id']}': {error}") from error
    summaries = []
    for correction in corrections:
        reports = [row["report"] for row in results if row["correction"] == correction]
        summaries.append(
            {
                "correction": correction,
                "case_count": len(reports),
                "evaluation_pixels": sum(report["evaluation_pixels"] for report in reports),
                **summarize([report["evaluation"] for report in reports]),
            }
        )
    identity = [(row["case_id"], row["correction"], row["report"]["run_id"]) for row in results]
    return {
        "schema_version": "1.0",
        "software_version": __version__,
        "benchmark_id": hashlib.sha256(json.dumps(identity).encode()).hexdigest()[:16],
        "created_at": datetime.now(timezone.utc).isoformat(),
        "data_source": "synthetic_demo" if synthetic else "user_supplied_rgb_images",
        "manifest_sha256": hashlib.sha256(
            json.dumps(manifest, sort_keys=True).encode()
        ).hexdigest(),
        "settings": {
            "threshold": float(threshold),
            "minimum_region_pixels": int(min_pixels),
            "connectivity": int(connectivity),
            "corrections": corrections,
        },
        "case_count": len(manifest["cases"]),
        "summaries": summaries,
        "results": results,
        "warnings": [
            "Synthetic pipeline checks only; not evidence of satellite accuracy."
            if synthetic
            else "User-supplied imagery and reference annotations have not been independently verified.",
            "Pooled metrics weight pixels; macro means weight defined case metrics equally. Undefined metrics remain null.",
            "Keep tuning pairs separate from evaluation pairs. Independence between cases is not verified.",
        ],
    }


def benchmark_artifacts(benchmark):
    rows = []
    for result in benchmark["results"]:
        report = result["report"]
        rows.append(
            {
                "case_id": result["case_id"],
                "correction": result["correction"],
                **{
                    key: report[key]
                    for key in (
                        "run_id",
                        "valid_pixels",
                        "evaluation_pixels",
                        "evaluation_fraction_of_usable",
                        "changed_pixels",
                        "changed_fraction",
                        "candidate_regions",
                    )
                },
                **report["evaluation"],
            }
        )
    output = io.StringIO(newline="")
    writer = csv.DictWriter(output, fieldnames=list(rows[0]))
    writer.writeheader()
    writer.writerows(rows)
    return {
        "benchmark.json": (json.dumps(benchmark, indent=2, allow_nan=False) + "\n").encode("utf-8"),
        "cases.csv": output.getvalue().encode("utf-8"),
    }


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "manifest", type=Path, help="JSON manifest with annotated image-pair cases."
    )
    parser.add_argument(
        "--out", type=Path, default=Path("outputs/benchmark"), help="New or empty directory."
    )
    parser.add_argument("--threshold", type=float, default=35)
    parser.add_argument("--min-pixels", type=int, default=25)
    parser.add_argument("--connectivity", type=int, choices=[4, 8], default=4)
    parser.add_argument(
        "--corrections",
        nargs="+",
        choices=["none", "median_offset"],
        default=["none", "median_offset"],
    )
    args = parser.parse_args(argv)
    try:
        if args.out.exists() and (not args.out.is_dir() or any(args.out.iterdir())):
            raise ValueError(
                "Output directory must be new or empty to preserve previous benchmarks."
            )
        benchmark = run_benchmark(
            args.manifest,
            threshold=args.threshold,
            min_pixels=args.min_pixels,
            connectivity=args.connectivity,
            corrections=args.corrections,
        )
        artifacts = benchmark_artifacts(benchmark)
        args.out.mkdir(parents=True, exist_ok=True)
        for name, content in artifacts.items():
            (args.out / name).write_bytes(content)
        print(json.dumps(benchmark["summaries"], indent=2, allow_nan=False))
        print(f"Benchmark saved to {args.out.resolve()}")
    except (OSError, ValueError) as error:
        parser.error(str(error))


if __name__ == "__main__":
    main()
