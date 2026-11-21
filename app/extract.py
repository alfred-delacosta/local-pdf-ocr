# Copyright Advanced Software and AI Solutions LLC
"""Shared extraction pipeline for JSON and NDJSON responses."""

from __future__ import annotations

import time
from collections.abc import Iterator
from dataclasses import dataclass
from typing import Any

from app.config import AppConfig
from app.lmstudio import LMStudioClient
from app.logging_safe import get_logger, short_id
from app.pdf_router import PageResult, iter_image_ocr, iter_pdf_pages
from app.security import detect_file_type

log = get_logger(__name__)


@dataclass
class ExtractResult:
    text: str
    pages: list[PageResult]
    model: str
    duration_ms: int
    file_name: str
    file_type: str
    page_count: int

    def to_public(self) -> dict[str, Any]:
        return {
            "text": self.text,
            "pages": [p.to_public() for p in self.pages],
            "model": self.model,
            "durationMs": self.duration_ms,
            "file": {
                "name": self.file_name,
                "type": self.file_type,
                "pageCount": self.page_count,
            },
        }


def safe_display_name(name: str | None) -> str:
    if not name:
        return "upload"
    base = name.replace("\\", "/").split("/")[-1]
    if len(base) > 64:
        return base[:61] + "..."
    return base or "upload"


def run_extract_events(
    data: bytes,
    filename: str | None,
    pages_spec: str | None,
    force_ocr: bool,
    cfg: AppConfig,
    client: LMStudioClient,
) -> Iterator[dict[str, Any]]:
    """Yield NDJSON-shaped events: page..., then done."""
    job_id = short_id()
    log.info("extract_start id=%s", job_id)
    started = time.perf_counter()
    detected = detect_file_type(data)
    display_name = safe_display_name(filename)
    pages: list[PageResult] = []

    if detected.kind == "pdf":
        import pypdfium2 as pdfium

        pdf = pdfium.PdfDocument(data)
        try:
            page_count = len(pdf)
        finally:
            pdf.close()
        iterator = iter_pdf_pages(data, pages_spec, force_ocr, cfg, client)
        file_type = "pdf"
    else:
        page_count = 1
        iterator = iter_image_ocr(data, detected, cfg, client)
        file_type = detected.kind

    for page in iterator:
        pages.append(page)
        event = {"type": "page", **page.to_public()}
        yield event

    duration_ms = int((time.perf_counter() - started) * 1000)
    joined = "\n\n".join(p.text for p in pages if p.text)
    result = ExtractResult(
        text=joined,
        pages=pages,
        model=client.model_id,
        duration_ms=duration_ms,
        file_name=display_name,
        file_type=file_type,
        page_count=page_count,
    )
    log.info(
        "extract_done id=%s pages=%s duration_ms=%s",
        job_id,
        len(pages),
        duration_ms,
    )
    done = {"type": "done", **result.to_public()}
    yield done


def run_extract(
    data: bytes,
    filename: str | None,
    pages_spec: str | None,
    force_ocr: bool,
    cfg: AppConfig,
    client: LMStudioClient,
) -> ExtractResult:
    final: ExtractResult | None = None
    for event in run_extract_events(data, filename, pages_spec, force_ocr, cfg, client):
        if event.get("type") == "done":
            pages = [
                PageResult(
                    page=p["page"],
                    source=p["source"],
                    text=p.get("text", ""),
                    error=p.get("error"),
                )
                for p in event["pages"]
            ]
            final = ExtractResult(
                text=event["text"],
                pages=pages,
                model=event["model"],
                duration_ms=event["durationMs"],
                file_name=event["file"]["name"],
                file_type=event["file"]["type"],
                page_count=event["file"]["pageCount"],
            )
    assert final is not None
    return final
