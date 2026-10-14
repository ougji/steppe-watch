"""One image-loading policy for the CLI and Streamlit interface."""

import io
import warnings

import numpy as np
from PIL import Image, ImageOps, UnidentifiedImageError

MAX_PIXELS = 4_000_000
MAX_FILE_BYTES = 25 * 1024 * 1024


def load_image(source, *, mask=False):
    """Read paths, bytes, or uploads with size limits and EXIF orientation.

    Reject transparency and high bit depth instead of silently corrupting nodata
    or radiometry. Grayscale mask values >127 select pixels.
    """
    if isinstance(source, bytes):
        data = source
    elif hasattr(source, "read"):
        source.seek(0)
        data = source.read(MAX_FILE_BYTES + 1)
    else:
        with open(source, "rb") as handle:
            data = handle.read(MAX_FILE_BYTES + 1)
    if len(data) > MAX_FILE_BYTES:
        raise ValueError("Each image must be at most 25 MiB.")
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("error", Image.DecompressionBombWarning)
            with Image.open(io.BytesIO(data)) as image:
                if image.format not in ("PNG", "JPEG"):
                    raise ValueError("Use an 8-bit PNG or JPEG image.")
                if image.width * image.height > MAX_PIXELS:
                    raise ValueError("Use a crop of at most 4 million pixels.")
                if (
                    image.mode in ("I", "F")
                    or image.mode.startswith("I;16")
                    or (image.format == "PNG" and len(data) > 24 and data[24] == 16)
                ):
                    raise ValueError(
                        "16-bit and floating-point imagery is unsupported; prepare an 8-bit crop."
                    )
                if "A" in image.getbands() or "transparency" in image.info:
                    alpha = np.asarray(image.convert("RGBA"))[:, :, 3]
                    if (alpha != 255).any():
                        raise ValueError(
                            "Transparent pixels are unsupported. Flatten the image and supply a usable-pixel mask."
                        )
                image = ImageOps.exif_transpose(image)
                rgb = np.array(image.convert("RGB"))
                if mask:
                    if not (
                        (rgb[:, :, 0] == rgb[:, :, 1]).all()
                        and (rgb[:, :, 1] == rgb[:, :, 2]).all()
                    ):
                        raise ValueError(
                            "Masks must be grayscale: white = selected, black = excluded."
                        )
                    return rgb[:, :, 0] > 127
                return rgb
    except (
        UnidentifiedImageError,
        Image.DecompressionBombError,
        Image.DecompressionBombWarning,
    ) as error:
        raise ValueError("Cannot decode a safe PNG/JPEG image.") from error


def png_bytes(array):
    output = io.BytesIO()
    if array.dtype == np.bool_:
        array = array.astype(np.uint8) * 255
    Image.fromarray(array).save(output, format="PNG")
    return output.getvalue()
