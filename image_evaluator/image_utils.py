from __future__ import annotations

from io import BytesIO

from PIL import Image


def extract_image_metadata(uploaded_file) -> tuple[int, int, int]:
    uploaded_file.seek(0)
    data = uploaded_file.read()
    uploaded_file.seek(0)
    with Image.open(BytesIO(data)) as img:
        width, height = img.size
    return len(data), width, height
