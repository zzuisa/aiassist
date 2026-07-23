"""Image upload validation and derivative sanitization helpers (US5).

Validation is layered: declared MIME, magic bytes, and a real decode with a
pixel-count guard against decompression bombs. Derivative generation strips all
EXIF/XMP/IPTC/GPS after applying orientation, and re-opens the output to confirm
metadata removal. The raw original is never modified in place.
"""

from __future__ import annotations

import io

from PIL import Image, ImageOps

from app.core.config import get_settings
from app.core.errors import ValidationError

# Magic byte prefixes for allowed image types.
_MAGIC = {
    b"\xff\xd8\xff": "image/jpeg",
    b"\x89PNG\r\n\x1a\n": "image/png",
    b"RIFF": "image/webp",  # followed by 'WEBP' at offset 8
}


def sniff_media_type(data: bytes) -> str | None:
    if data[:3] == b"\xff\xd8\xff":
        return "image/jpeg"
    if data[:8] == b"\x89PNG\r\n\x1a\n":
        return "image/png"
    if data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return "image/webp"
    return None


def validate_image(data: bytes, declared_type: str) -> tuple[int, int]:
    """Validate declared type == magic bytes == real decode; guard pixel bombs.

    Returns (width, height). Raises ValidationError on any mismatch/abuse.
    """
    settings = get_settings()
    sniffed = sniff_media_type(data)
    if sniffed is None:
        raise ValidationError("Unrecognized image content", code="unsupported_media", status=415)
    if declared_type != sniffed:
        raise ValidationError(
            "Declared type does not match content", code="mime_mismatch", status=415
        )
    try:
        # Pillow's decompression-bomb guard: raise instead of warn.
        Image.MAX_IMAGE_PIXELS = settings.upload_image_max_pixels
        with Image.open(io.BytesIO(data)) as img:
            img.verify()  # structural check
        with Image.open(io.BytesIO(data)) as img2:
            width, height = img2.size
            if width * height > settings.upload_image_max_pixels:
                raise ValidationError("Image exceeds pixel limit", code="pixel_bomb", status=413)
    except ValidationError:
        raise
    except Exception as exc:  # corrupt / malformed image
        raise ValidationError("Corrupt or invalid image", code="invalid_image", status=415) from exc
    return width, height


def make_sanitized_derivative(data: bytes, *, max_size: int, fmt: str = "WEBP") -> bytes:
    """Return a metadata-stripped, orientation-corrected derivative.

    Orientation MUST be applied before stripping EXIF (otherwise rotation is lost).
    """
    with Image.open(io.BytesIO(data)) as opened:
        oriented = ImageOps.exif_transpose(opened)  # apply orientation first
        rgb = oriented.convert("RGB")
        rgb.thumbnail((max_size, max_size))
        out = io.BytesIO()
        # Saving without an exif/icc argument drops all metadata.
        rgb.save(out, format=fmt, quality=82)
    derivative = out.getvalue()
    _assert_no_metadata(derivative)
    return derivative


def _assert_no_metadata(data: bytes) -> None:
    with Image.open(io.BytesIO(data)) as img:
        exif = img.getexif()
        if exif and len(exif):
            raise ValidationError("Derivative still contains metadata", code="metadata_leak")
