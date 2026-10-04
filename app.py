import io
import json

import numpy as np
from PIL import Image, ImageOps, UnidentifiedImageError
import streamlit as st

from change_watch.core import detect_changes, evaluate_mask, make_overlay
from change_watch.demo import synthetic_pair


def load_upload(upload, mode="RGB"):
    with Image.open(upload) as image:
        if image.width * image.height > 4_000_000:
            raise ValueError("Use a crop of at most 4 million pixels for this starter.")
        return np.array(ImageOps.exif_transpose(image).convert(mode))


def png_bytes(array):
    output = io.BytesIO()
    Image.fromarray(array).save(output, format="PNG")
    return output.getvalue()


st.set_page_config(page_title="Steppe Watch", page_icon="🛰️", layout="wide")
st.title("Steppe Watch")
st.write("Compare two aligned images and highlight candidate visual changes for inspection.")
st.caption("Prototype · RGB difference baseline · No trained model yet")

with st.sidebar:
    st.header("Compare images")
    source = st.radio("Image source", ["Synthetic demo", "Upload images"])
    threshold = st.slider("Difference threshold", 0, 255, 35, help="Mean absolute difference across red, green and blue. Higher values retain stronger changes.")
    min_pixels = st.slider("Minimum region size (pixels)", 1, 500, 25)
    st.caption("Regions use four-connected pixels. Changed percentage is measured over the usable mask.")

truth, valid = None, None
if source == "Synthetic demo":
    before, after, truth = synthetic_pair()
    st.info("These images are generated illustrations. They are not satellite observations or evidence about any real mine.")
else:
    st.write("Use RGB PNG/JPEG crops of the same area, aligned to the same pixel grid. Matching dimensions alone do not establish alignment.")
    c1, c2 = st.columns(2)
    with c1:
        before_file = st.file_uploader("Before image", type=["png", "jpg", "jpeg"])
    with c2:
        after_file = st.file_uploader("After image", type=["png", "jpg", "jpeg"])
    valid_file = st.file_uploader("Optional usable-pixel mask (white = usable on both dates)", type=["png"])
    if not before_file or not after_file:
        st.info("Upload both images to run the comparison.")
        st.stop()
    if not st.checkbox("I checked that both images cover the same area and are aligned."):
        st.info("Confirm image alignment before comparing.")
        st.stop()
    try:
        before, after = load_upload(before_file), load_upload(after_file)
        if valid_file:
            valid = load_upload(valid_file, "L") > 127
    except (ValueError, OSError, UnidentifiedImageError, Image.DecompressionBombError) as error:
        st.error(f"Cannot read image: {error}")
        st.stop()

try:
    result = detect_changes(before, after, threshold, min_pixels, valid)
except ValueError as error:
    st.error(str(error))
    st.stop()

report = dict(result.summary)
report["data_source"] = "synthetic_demo" if truth is not None else "user_supplied_rgb_images"
if truth is not None:
    report["evaluation"] = evaluate_mask(result.mask, truth)
    report["evaluation_scope"] = "Synthetic pipeline check only; not evidence of real-world accuracy."

c1, c2, c3 = st.columns(3)
c1.metric("Flagged pixels", f"{result.summary['changed_pixels']:,}")
c2.metric("Usable pixels flagged", f"{result.summary['changed_fraction']:.1%}")
c3.metric("Candidate regions", result.summary["candidate_regions"])

c1, c2, c3 = st.columns(3)
c1.image(before, caption="Before", width="stretch")
c2.image(after, caption="After", width="stretch")
c3.image(make_overlay(after, result.mask), caption="Orange = candidate change", width="stretch")

with st.expander("Difference map and binary change mask"):
    c1, c2 = st.columns(2)
    c1.image(result.score.astype(np.uint8), caption="RGB difference, 0–255", width="stretch")
    c2.image(result.mask.astype(np.uint8) * 255, caption="White = flagged", width="stretch")

c1, c2 = st.columns(2)
c1.download_button("Download change mask", png_bytes(result.mask.astype(np.uint8) * 255), "change_mask.png", "image/png")
c2.download_button("Download report", json.dumps(report, indent=2), "report.json", "application/json")

st.warning("Clouds, shadows, seasons, exposure and image shifts can cause false alerts. A flagged region does not establish mining activity or illegality.")
with st.expander("What this version can demonstrate"):
    st.write("An end-to-end, reproducible comparison pipeline. The next milestone is one real location with documented imagery, cloud exclusions and reference annotations.")
    st.write("The synthetic mask lets us check the pipeline. It provides no estimate of performance on real satellite imagery.")
