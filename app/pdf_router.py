# Copyright Advanced Software and AI Solutions LLC
"""PDF page routing: text layer vs OCR render, and image prep."""

from __future__ import annotations

import io
import re
from collections.abc import Iterator
from dataclasses import dataclass
from typing import Literal

import pypdfium2 as pdfium
from PIL import Image

from app.config import AppConfig
from app.lmstudio import LMStudioClient, LMStudioError
from app.logging_safe import get_logger
from app.security import DetectedFile, UploadValidationError

log = get_logger(__name__)

SourceKind = Literal["text-layer", "ocr"]

# Pillow decompression bomb guard
Image.MAX_IMAGE_PIXELS = 40_000_000

_NON_PRINTABLE_RE = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f-\x9f\ufffd]")


@dataclass
class PageResult:
    page: int
    source: SourceKind
    text: str
    error: str | None = None

    def to_public(self) -> dict:
        out = {"page": self.page, "source": self.source, "text": self.text}
        if self.error:
            out["error"] = self.error
        return out


def parse_pages_spec(spec: str | None, page_count: int, max_pages: int) -> list[int]:
    if page_count < 1:
        raise UploadValidationError(400, "empty_pdf", "PDF has no pages.")
    if page_count > max_pages and not spec:
        raise UploadValidationError(
            422,
            "too_many_pages",
            f"PDF has {page_count} pages; maximum is {max_pages}. Use the pages field.",
        )
    if not spec or not spec.strip():
        if page_count > max_pages:
            raise UploadValidationError(
                422,
                "too_many_pages",
                f"PDF has {page_count} pages; maximum is {max_pages}.",
            )
        return list(range(1, page_count + 1))

    selected: set[int] = set()
    for part in spec.split(","):
        token = part.strip()
        if not token:
            continue
        if "-" in token:
            start_s, _, end_s = token.partition("-")
            try:
                start = int(start_s.strip())
                end = int(end_s.strip())
            except ValueError as exc:
                raise UploadValidationError(
                    422, "invalid_pages", f"Invalid pages range: {token!r}."
                ) from exc
            if start < 1 or end < start:
                raise UploadValidationError(
                    422, "invalid_pages", f"Invalid pages range: {token!r}."
                )
            for n in range(start, end + 1):
                selected.add(n)
        else:
            try:
                n = int(token)
            except ValueError as exc:
                raise UploadValidationError(
                    422, "invalid_pages", f"Invalid page number: {token!r}."
                ) from exc
            selected.add(n)

    if not selected:
        raise UploadValidationError(422, "invalid_pages", "No pages selected.")
    if len(selected) > max_pages:
        raise UploadValidationError(
            422,
            "too_many_pages",
            f"Requested {len(selected)} pages; maximum is {max_pages}.",
        )
    for n in selected:
        if n < 1 or n > page_count:
            raise UploadValidationError(
                422,
                "invalid_pages",
                f"Page {n} is out of range (1-{page_count}).",
            )
    return sorted(selected)


def is_garbled(text: str) -> bool:
    if not text:
        return True
    bad = len(_NON_PRINTABLE_RE.findall(text))
    return (bad / max(len(text), 1)) > 0.15


def text_layer_usable(text: str, min_chars: int) -> bool:
    cleaned = text.strip()
    if len(cleaned) < min_chars:
        return False
    return not is_garbled(cleaned)


def shrink_image(img: Image.Image, max_edge: int) -> Image.Image:
    w, h = img.size
    longest = max(w, h)
    if longest <= max_edge:
        return img
    scale = max_edge / float(longest)
    new_size = (max(1, int(w * scale)), max(1, int(h * scale)))
    return img.resize(new_size, Image.Resampling.LANCZOS)


def image_to_png_bytes(img: Image.Image, max_edge: int) -> bytes:
    prepared = shrink_image(img.convert("RGB"), max_edge)
    buf = io.BytesIO()
    prepared.save(buf, format="PNG")
    return buf.getvalue()


def load_image_bytes(data: bytes) -> Image.Image:
    img = Image.open(io.BytesIO(data))
    img.load()
    return img


def extract_page_text(page: pdfium.PdfPage) -> str:
    textpage = page.get_textpage()
    try:
        return textpage.get_text_bounded() or ""
    finally:
        textpage.close()


def render_page_png(page: pdfium.PdfPage, dpi: int, max_edge: int) -> bytes:
    scale = dpi / 72.0
    bitmap = page.render(scale=scale)
    try:
        pil = bitmap.to_pil()
        return image_to_png_bytes(pil, max_edge)
    finally:
        bitmap.close()


def iter_pdf_pages(
    data: bytes,
    pages_spec: str | None,
    force_ocr: bool,
    cfg: AppConfig,
    client: LMStudioClient,
) -> Iterator[PageResult]:
    pdf = pdfium.PdfDocument(data)
    try:
        page_count = len(pdf)
        pages = parse_pages_spec(pages_spec, page_count, cfg.max_pages)
        for page_num in pages:
            page = pdf[page_num - 1]
            try:
                if not force_ocr:
                    layer = extract_page_text(page)
                    if text_layer_usable(layer, cfg.text_layer_min_chars):
                        yield PageResult(page=page_num, source="text-layer", text=layer.strip())
                        continue
                try:
                    png = render_page_png(page, cfg.render_dpi, cfg.render_max_edge)
                    text = client.ocr_image(png, mime="image/png")
                    yield PageResult(page=page_num, source="ocr", text=text)
                except LMStudioError as exc:
                    log.info("ocr_page_failed page=%s code=%s", page_num, exc.code)
                    yield PageResult(
                        page=page_num,
                        source="ocr",
                        text="",
                        error=exc.message,
                    )
            finally:
                page.close()
    finally:
        pdf.close()


def iter_image_ocr(
    data: bytes,
    detected: DetectedFile,
    cfg: AppConfig,
    client: LMStudioClient,
) -> Iterator[PageResult]:
    try:
        img = load_image_bytes(data)
        png = image_to_png_bytes(img, cfg.render_max_edge)
        text = client.ocr_image(png, mime="image/png")
        yield PageResult(page=1, source="ocr", text=text)
    except LMStudioError as exc:
        log.info("ocr_image_failed code=%s", exc.code)
        yield PageResult(page=1, source="ocr", text="", error=exc.message)
    except OSError as exc:
        raise UploadValidationError(
            400, "invalid_image", "Could not decode the uploaded image."
        ) from exc
