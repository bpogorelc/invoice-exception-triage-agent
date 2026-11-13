"""Local PDF text extraction and Gemini structured invoice capture."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Optional

from pypdf import PdfReader

from invoice_exception_triage_agent.config import get_settings
from invoice_exception_triage_agent.data_store import list_invoice_pdfs, load_extracted_fixture
from invoice_exception_triage_agent.models import ExtractedInvoice, InvoiceLine


INVOICE_ID_RE = re.compile(r"\b(INV-[A-Z0-9-]+)\b", re.IGNORECASE)


def parse_invoice_id_from_message(message: str) -> Optional[str]:
    match = INVOICE_ID_RE.search(message or "")
    if not match:
        return None
    return match.group(1).upper()


def extract_pdf_text_by_page(pdf_path: Path) -> list[tuple[int, str]]:
    reader = PdfReader(str(pdf_path))
    pages: list[tuple[int, str]] = []
    for index, page in enumerate(reader.pages, start=1):
        text = page.extract_text() or ""
        pages.append((index, text))
    return pages


def _heuristic_extract(invoice_id: str, pages: list[tuple[int, str]], pdf_path: Path) -> ExtractedInvoice:
    """Deterministic fallback when Gemini credentials are unavailable."""
    joined = "\n".join(text for _, text in pages)
    supplier_match = re.search(r"Supplier:\s*(.+)", joined)
    po_match = re.search(r"Purchase Order:\s*(PO-[A-Z0-9-]+)", joined, re.IGNORECASE)
    currency_match = re.search(r"Currency:\s*([A-Z]{3})", joined)
    line_match = re.search(
        r"(SKU-[A-Z0-9]+).+?Qty\s+(\d+(?:\.\d+)?).+?Unit\s+EUR\s+(\d+(?:\.\d+)?)",
        joined,
        re.IGNORECASE,
    )
    page_number = pages[0][0] if pages else None
    supporting = None
    if line_match:
        for page_no, text in pages:
            if line_match.group(0) in text or line_match.group(1) in text:
                page_number = page_no
                supporting = next(
                    (ln.strip() for ln in text.splitlines() if line_match.group(1) in ln),
                    line_match.group(0),
                )
                break

    line = InvoiceLine(
        sku=line_match.group(1).upper() if line_match else None,
        quantity=line_match.group(2) if line_match else None,
        unit_price=line_match.group(3) if line_match else None,
        page_number=page_number,
        supporting_text=supporting,
    )
    return ExtractedInvoice(
        invoice_id=invoice_id,
        supplier=supplier_match.group(1).strip() if supplier_match else None,
        po_reference=po_match.group(1).upper() if po_match else None,
        currency=currency_match.group(1).upper() if currency_match else None,
        lines=[line],
        source_pdf=str(pdf_path.name),
        extraction_mode="pdf_heuristic",
    )


def _gemini_structured_extract(invoice_id: str, pages: list[tuple[int, str]], pdf_path: Path) -> ExtractedInvoice:
    from google import genai
    from google.genai import types

    settings = get_settings()
    page_blob = "\n\n".join(f"--- PAGE {page_no} ---\n{text}" for page_no, text in pages)
    prompt = (
        "Extract supplier invoice fields from the searchable PDF text below. "
        "Return only values present in the text. Missing values must be null. "
        "For each line retain page_number and supporting_text from the source page.\n\n"
        f"Expected invoice id hint: {invoice_id}\n\n{page_blob}"
    )

    if settings.google_api_key and not settings.google_genai_use_vertexai:
        client = genai.Client(api_key=settings.google_api_key)
    else:
        client = genai.Client(
            vertexai=True,
            project=settings.google_cloud_project or None,
            location=settings.google_cloud_location,
        )

    response = client.models.generate_content(
        model=settings.model_name,
        contents=prompt,
        config=types.GenerateContentConfig(
            response_mime_type="application/json",
            response_schema=ExtractedInvoice,
        ),
    )
    raw = response.parsed
    if isinstance(raw, ExtractedInvoice):
        invoice = raw
    else:
        payload = json.loads(response.text)
        invoice = ExtractedInvoice.model_validate(payload)
    invoice.source_pdf = pdf_path.name
    invoice.extraction_mode = "gemini_structured"
    if not invoice.invoice_id:
        invoice.invoice_id = invoice_id
    return invoice


def read_invoice_document(invoice_id: str, *, prefer_live_extraction: bool = False) -> ExtractedInvoice:
    """Read invoice PDF (when present) and validate with Pydantic.

    Offline tests use fixture JSON. Live demo may call Gemini structured output.
    """
    invoice_id = invoice_id.upper()
    pdfs = list_invoice_pdfs()
    pdf_path = pdfs.get(invoice_id)

    if not prefer_live_extraction or not get_settings().has_credentials:
        fixture = load_extracted_fixture(invoice_id)
        if fixture is not None:
            return ExtractedInvoice.model_validate(fixture)
        if pdf_path is None:
            raise FileNotFoundError(f"No PDF or extracted fixture for {invoice_id}")
        pages = extract_pdf_text_by_page(pdf_path)
        return _heuristic_extract(invoice_id, pages, pdf_path)

    if pdf_path is None:
        fixture = load_extracted_fixture(invoice_id)
        if fixture is None:
            raise FileNotFoundError(f"No PDF or extracted fixture for {invoice_id}")
        return ExtractedInvoice.model_validate(fixture)

    pages = extract_pdf_text_by_page(pdf_path)
    try:
        return _gemini_structured_extract(invoice_id, pages, pdf_path)
    except Exception:
        # Keep the demo runnable if the model call fails; still validate via Pydantic.
        return _heuristic_extract(invoice_id, pages, pdf_path)
