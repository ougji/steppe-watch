import io
import unittest
from unittest.mock import patch

import numpy as np
from PIL import Image

from change_watch.io import load_image, png_bytes


class InputTests(unittest.TestCase):
    def test_paths_bytes_and_file_objects_decode_the_same(self):
        image = np.full((5, 7, 3), 123, dtype=np.uint8)
        data = png_bytes(image)
        upload = io.BytesIO(data)
        upload.seek(len(data))
        np.testing.assert_array_equal(load_image(upload), image)
        np.testing.assert_array_equal(load_image(data), image)

    def test_mask_boundary(self):
        mask = np.array([[0, 127, 128, 255]], dtype=np.uint8)
        np.testing.assert_array_equal(
            load_image(png_bytes(mask), mask=True), [[False, False, True, True]]
        )

    def test_colour_mask_rejected(self):
        image = np.zeros((2, 2, 3), dtype=np.uint8)
        image[0, 0] = [255, 0, 0]
        with self.assertRaisesRegex(ValueError, "grayscale"):
            load_image(png_bytes(image), mask=True)

    def test_transparent_pixels_rejected(self):
        image = np.zeros((2, 2, 4), dtype=np.uint8)
        with self.assertRaisesRegex(ValueError, "Transparent"):
            load_image(png_bytes(image))

    def test_opaque_rgba_is_accepted(self):
        image = np.full((2, 2, 4), 255, dtype=np.uint8)
        self.assertEqual(load_image(png_bytes(image)).shape, (2, 2, 3))

    def test_high_bit_depth_rejected(self):
        with self.assertRaisesRegex(ValueError, "16-bit"):
            load_image(png_bytes(np.zeros((2, 2), dtype=np.uint16)))

    def test_size_limits(self):
        data = png_bytes(np.zeros((5, 5, 3), dtype=np.uint8))
        with patch("change_watch.io.MAX_PIXELS", 20), self.assertRaisesRegex(ValueError, "million"):
            load_image(data)
        with patch("change_watch.io.MAX_FILE_BYTES", 10), self.assertRaisesRegex(ValueError, "MiB"):
            load_image(data)

    def test_exif_orientation_is_applied(self):
        image = Image.fromarray(np.zeros((3, 5, 3), dtype=np.uint8))
        exif = image.getexif()
        exif[274] = 6
        output = io.BytesIO()
        image.save(output, format="JPEG", exif=exif)
        self.assertEqual(load_image(output.getvalue()).shape, (5, 3, 3))

    def test_corrupt_and_unsupported_inputs_rejected(self):
        with self.assertRaises(ValueError):
            load_image(b"not an image")
        output = io.BytesIO()
        Image.new("RGB", (2, 2)).save(output, format="BMP")
        with self.assertRaisesRegex(ValueError, "PNG or JPEG"):
            load_image(output.getvalue())
