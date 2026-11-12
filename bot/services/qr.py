from __future__ import annotations

import io

import segno


def make_qr_bytes(url: str) -> bytes:
    """
    Generate a QR code PNG from a subscription URL.
    Returns raw bytes suitable for aiogram BufferedInputFile.
    """
    qr = segno.make(url, error="M")
    buf = io.BytesIO()
    qr.save(
        buf,
        kind="png",
        scale=8,       # ~350×350 px — crisp on mobile
        border=2,
        light="#FFFFFF",
        dark="#000000",
    )
    return buf.getvalue()
