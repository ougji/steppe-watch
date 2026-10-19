"""Steppe Watch: a reproducible image-change review workbench."""

import json

import numpy as np
import streamlit as st

from change_watch import __version__
from change_watch.analysis import analyze_pair, array_fingerprint
from change_watch.core import make_overlay
from change_watch.demo import synthetic_pair
from change_watch.export import build_artifacts, regions_csv, zip_artifacts
from change_watch.io import load_image, png_bytes


# Streamlit may sample large ndarray keys by default. Hash every pixel so a
# small local change in a large upload cannot reuse another image's result.
@st.cache_data(
    max_entries=2, ttl=900, show_spinner=False, hash_funcs={np.ndarray: array_fingerprint}
)
def run_analysis(before, after, **options):
    return analyze_pair(before, after, **options)


def image_columns(images):
    for column, (array, caption) in zip(st.columns(len(images)), images):
        column.image(array, caption=caption, width="stretch")


def main():
    st.set_page_config(page_title="Steppe Watch | Change explorer", page_icon="🛰️", layout="wide")
    st.markdown(
        """
    <style>
    .block-container {max-width: 1440px; padding: 4.5rem 2rem 2rem;}
    .sw-hero {padding: 1.6rem 2rem; border-radius: 18px;
      background: #173D30; color: #FAFAF3; margin-bottom: 1.5rem;}
    .sw-hero h1 {color: #FAFAF3; padding: .2rem 0 .4rem; font-size: 2.6rem;}
    .sw-hero p {color: #D6E6D4; margin: 0; max-width: 760px;}
    .sw-kicker {font-size: .75rem; letter-spacing: .16em; color: #C5D993;}
    [data-testid="stMetric"] {background: #FFFFFF; border: 1px solid #DFE6D9;
      border-radius: 12px; padding: 1rem;}
    @media (max-width: 1100px) {
      [data-testid="stHorizontalBlock"]:has([data-testid="stMetric"]) {flex-wrap: wrap;}
      [data-testid="stColumn"]:has([data-testid="stMetric"]) {flex: 1 1 calc(50% - 1rem); min-width: 180px;}
    }
    </style>
    <div class="sw-hero"><div class="sw-kicker">LAND CHANGE · KAZAKHSTAN PILOT</div>
    <h1>Steppe Watch</h1><p>See what changed. Inspect the evidence.<br>
    A reproducible workspace for comparing satellite image crops.</p></div>
    """,
        unsafe_allow_html=True,
    )

    with st.sidebar:
        st.header("Your comparison")
        source = st.radio("Image source", ["Synthetic demo", "Upload images"], key="source")
        if source == "Synthetic demo":
            scenario = st.selectbox(
                "Demo scenario",
                ["Quarry expansion", "Expansion + brightness shift"],
                key="scenario",
            )
        st.divider()
        st.subheader("Detection settings")
        threshold = st.slider(
            "Difference threshold",
            0,
            255,
            35,
            key="threshold",
            help="Flag scores strictly above this value. Higher thresholds retain stronger differences.",
        )
        min_pixels = st.number_input(
            "Minimum region size (pixels)", 1, 4_000_000, 25, key="min_pixels"
        )
        connectivity = st.selectbox(
            "Connected neighbours",
            [4, 8],
            key="connectivity",
            help="4 uses shared edges; 8 also connects diagonal pixels.",
        )
        correction_enabled = st.checkbox(
            "Correct global brightness offset",
            key="correction",
            help="Subtract the median RGB offset over usable pixels. Experimental: assumes most land is stable.",
        )
        sensitivity = st.checkbox("Compare nearby thresholds", key="sensitivity")
        st.caption(
            "Settings update the result automatically. Scores describe RGB differences, not probabilities."
        )
        st.divider()
        st.caption(
            f"Steppe Watch {__version__} · RGB baseline\n\nNo trained model or automatic alignment."
        )

    truth, valid, evaluation_mask, metadata = None, None, None, {}
    synthetic = source == "Synthetic demo"
    if synthetic:
        before, after, truth = synthetic_pair()
        if scenario == "Expansion + brightness shift":
            after = np.clip(after.astype(np.int16) + 45, 0, 255).astype(np.uint8)
        st.info(
            "SYNTHETIC DEMO · Generated terrain and an artificial quarry expansion. These are not satellite observations."
        )
    else:
        st.subheader("1 · Add aligned imagery")
        st.caption(
            "PNG/JPEG · 8-bit · up to 4 million pixels and 25 MiB per file. Prepare both dates on the same pixel grid."
        )
        left, right = st.columns(2)
        before_file = left.file_uploader("Before image", type=["png", "jpg", "jpeg"], key="before")
        after_file = right.file_uploader("After image", type=["png", "jpg", "jpeg"], key="after")
        with st.expander("Usable pixels and reference annotations"):
            valid_file = st.file_uploader(
                "Usable-pixel mask (optional)",
                type=["png"],
                key="valid",
                help="White = usable on BOTH dates. Black excludes clouds, shadows and missing data.",
            )
            truth_file = st.file_uploader(
                "Reference change mask (optional)",
                type=["png"],
                key="truth",
                help="White = known change; black = known unchanged. Use annotation coverage to exclude unknown labels.",
            )
            evaluation_file = st.file_uploader(
                "Annotation coverage mask (optional)",
                type=["png"],
                key="evaluation_mask",
                help="White = labelled; black = unknown. Requires a reference mask. Detection still uses all usable pixels.",
            )
        with st.expander("Record image provenance"):
            metadata["site"] = st.text_input("Site or experiment name", max_chars=200)
            metadata["source"] = st.text_input("Imagery provider / source URL", max_chars=2000)
            first, second = st.columns(2)
            metadata["before_date"] = first.text_input("Before date (YYYY-MM-DD)", max_chars=10)
            metadata["after_date"] = second.text_input("After date (YYYY-MM-DD)", max_chars=10)
            metadata["notes"] = st.text_area(
                "Processing, license and annotation notes", max_chars=4000
            )
        if not before_file or not after_file:
            st.info(
                "Add a before and after image to start, or explore the synthetic demo from the sidebar."
            )
            st.stop()
        if not st.checkbox(
            "I checked that both images cover the same area and are aligned.", key="aligned"
        ):
            st.info(
                "Check geographic alignment before comparing. Equal image dimensions alone are not enough."
            )
            st.stop()
        try:
            before, after = load_image(before_file), load_image(after_file)
            valid = load_image(valid_file, mask=True) if valid_file else None
            truth = load_image(truth_file, mask=True) if truth_file else None
            evaluation_mask = load_image(evaluation_file, mask=True) if evaluation_file else None
        except (ValueError, OSError) as error:
            st.error(f"Cannot read image: {error}")
            st.stop()

    correction = "median_offset" if correction_enabled else "none"
    try:
        with st.spinner("Comparing usable pixels…"):
            analysis = run_analysis(
                before,
                after,
                threshold=threshold,
                min_pixels=min_pixels,
                valid_mask=valid,
                truth=truth,
                evaluation_mask=evaluation_mask,
                connectivity=connectivity,
                correction=correction,
                synthetic=synthetic,
                metadata=metadata,
                sensitivity=sensitivity,
            )
    except ValueError as error:
        st.error(str(error))
        st.stop()
    result, report = analysis.result, analysis.report
    overlay = make_overlay(after, result.mask)
    # Exclusions have an explicit visual treatment instead of resembling stable land.
    overlay[~result.valid] = [105, 117, 130]
    st.caption(
        f"{report['width']:,} × {report['height']:,} pixels · {report['valid_pixels']:,} usable · Run {report['run_id']}"
    )
    columns = st.columns(4)
    columns[0].metric("Usable pixels flagged", f"{report['changed_fraction']:.1%}")
    columns[1].metric("Flagged pixels", f"{report['changed_pixels']:,}")
    columns[2].metric("Candidate regions", f"{report['candidate_regions']:,}")
    columns[3].metric("Usable coverage", f"{report['usable_fraction']:.1%}")
    if correction_enabled:
        st.warning(
            "Brightness correction assumes most usable pixels are stable. Compare it with the baseline; it can hide widespread real change."
        )
        st.caption(
            "Estimated RGB offset: "
            + ", ".join(f"{value:+.1f}" for value in report["channel_offset_rgb"])
        )
    if report["usable_fraction"] < 0.5:
        st.warning(
            "Less than half the image is usable. The flagged percentage describes only that subset."
        )
    if not result.mask.any():
        st.info(
            "No regions pass these settings. This does not prove the site is unchanged; inspect the imagery and exclusions."
        )

    compare, regions, evaluation, experiment = st.tabs(
        ["Compare imagery", "Inspect regions", "Evaluate & tune", "Export experiment"]
    )
    with compare:
        st.subheader("The image pair, with evidence in view")
        image_columns(
            [(before, "Before"), (after, "After"), (overlay, "Orange = flagged · slate = excluded")]
        )
        with st.expander("Swipe between dates"):
            split = st.slider("Before image share (%)", 0, 100, 50, key="wipe")
            cut = round(before.shape[1] * split / 100)
            wipe = after.copy()
            wipe[:, :cut] = before[:, :cut]
            if 0 < cut < before.shape[1]:
                wipe[:, cut : cut + 1] = [255, 255, 255]
            st.image(wipe, caption="Before on the left · after on the right", width="stretch")
        with st.expander("Difference and masks"):
            image_columns(
                [
                    (result.score.astype(np.uint8), "Difference score · 0–255"),
                    (result.mask.astype(np.uint8) * 255, "White = retained change"),
                    (result.valid.astype(np.uint8) * 255, "White = usable on both dates"),
                ]
            )
            st.caption(
                f"{report['filtered_pixels']:,} above-threshold pixels were removed by the minimum region-size filter."
            )

    with regions:
        st.subheader("Review candidate regions")
        st.caption(
            "Largest regions first. Boxes use pixel coordinates; their right and bottom edges are exclusive."
        )
        if result.regions:
            st.dataframe(result.regions[:100], hide_index=True, width="stretch")
            if len(result.regions) > 100:
                st.caption(
                    "Table shows the largest 100 regions. The CSV contains every region; enter any region ID below."
                )
            region_id = st.number_input(
                "Region ID to inspect",
                1,
                len(result.regions),
                result.regions[0]["region_id"],
                key=f"region_{report['run_id']}",
            )
            region = next(row for row in result.regions if row["region_id"] == region_id)
            y0, y1 = max(0, region["y_min"] - 12), min(before.shape[0], region["y_max"] + 12)
            x0, x1 = max(0, region["x_min"] - 12), min(before.shape[1], region["x_max"] + 12)
            crop = np.s_[y0:y1, x0:x1]
            selected = make_overlay(after[crop], result.labels[crop] == region_id)
            image_columns(
                [
                    (before[crop], f"Region {region_id} · before"),
                    (after[crop], "After"),
                    (
                        selected,
                        f"{region['pixels']:,} pixels · mean score {region['mean_difference']:.1f}",
                    ),
                ]
            )
        else:
            st.write(
                "There are no retained candidate regions to inspect with the current settings."
            )
        st.download_button(
            "Download all regions (CSV)", regions_csv(result.regions), "regions.csv", "text/csv"
        )

    with evaluation:
        st.subheader("Measure against a reference")
        if truth is None:
            st.info(
                "Add a reference change mask to measure precision, recall, F1 and IoU. Flagged-pixel percentages are not accuracy metrics."
            )
        else:
            st.caption(report["evaluation_scope"])
            st.caption(
                f"Evaluated {report['evaluation_pixels']:,} annotated pixels "
                f"({report['evaluation_fraction_of_usable']:.1%} of usable coverage). "
                "Detection and flagged percentages still use all usable pixels."
            )
            for column, key in zip(st.columns(4), ("precision", "recall", "f1", "iou")):
                value = report["evaluation"][key]
                column.metric(
                    key.upper() if key in ("f1", "iou") else key.title(),
                    "Undefined" if value is None else f"{value:.3f}",
                )
            errors = np.full_like(after, [238, 241, 231])
            errors[result.mask & truth & result.valid] = [25, 123, 94]
            errors[result.mask & ~truth & result.valid] = [222, 96, 42]
            errors[~result.mask & truth & result.valid] = [65, 109, 184]
            errors[~analysis.evaluation_mask] = [105, 117, 130]
            image_columns(
                [
                    (truth.astype(np.uint8) * 255, "Reference · white = change"),
                    (
                        errors,
                        "Green = true positive · orange = false positive · blue = missed · slate = unevaluated",
                    ),
                ]
            )
            st.dataframe(
                [
                    {"Outcome": key.replace("_", " "), "Pixels": value}
                    for key, value in report["evaluation"].items()
                    if key.endswith("pixels")
                ],
                hide_index=True,
                width="stretch",
            )
        st.subheader("Sensitivity to the threshold")
        st.caption(
            "This comparison holds the images, exclusions, correction and minimum size fixed. It does not identify an optimal threshold. Keep tuning and evaluation data separate."
        )
        if "sensitivity" in report:
            st.line_chart(
                report["sensitivity"], x="threshold", y="changed_fraction", color="#176B52"
            )
            st.dataframe(report["sensitivity"], hide_index=True, width="stretch")
        else:
            st.write(
                "Enable “Compare nearby thresholds” in the sidebar to compute the sensitivity curve."
            )

    with experiment:
        st.subheader("An experiment someone else can reproduce")
        st.write(
            "The ZIP includes the decoded image pair, usable and reference masks, overlay, full-precision scores, region CSV, report, provenance and a rerun command."
        )
        st.caption(
            "Input images are included in the download. Check their redistribution terms before sharing the bundle."
        )
        if st.button("Prepare experiment bundle", type="primary", key="prepare"):
            with st.spinner("Packaging this comparison…"):
                st.session_state["bundle"] = (
                    report["run_id"],
                    zip_artifacts(build_artifacts(analysis, before, after, truth)),
                )
        bundle = st.session_state.get("bundle")
        if bundle and bundle[0] == report["run_id"]:
            st.download_button(
                "Download experiment ZIP",
                bundle[1],
                f"steppe-watch-{report['run_id']}.zip",
                "application/zip",
            )
        elif bundle:
            st.caption("Settings changed. Prepare a new bundle for the current result.")
        left, right = st.columns(2)
        left.download_button(
            "Download change mask", png_bytes(result.mask), "change_mask.png", "image/png"
        )
        right.download_button(
            "Download JSON report",
            json.dumps(report, indent=2, allow_nan=False),
            "report.json",
            "application/json",
        )
        with st.expander("Inspect the full report"):
            st.json(report)
    st.divider()
    st.caption(
        "For human review · Clouds, shadows, seasons, exposure and image shifts can cause false alerts. A flagged region does not establish mining activity or illegality."
    )


if __name__ == "__main__":
    main()
