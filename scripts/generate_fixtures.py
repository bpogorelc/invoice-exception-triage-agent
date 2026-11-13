"""Generate searchable supplier invoice PDFs and offline extraction JSON."""

from __future__ import annotations

import json
import sys
from pathlib import Path

from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from invoice_exception_triage_agent.config import FIXTURES_DIR  # noqa: E402

PDF_DIR = FIXTURES_DIR / "invoices"
EXTRACTED_DIR = FIXTURES_DIR / "extracted"


INVOICES = [
    {
        "invoice_id": "INV-1001",
        "supplier": "Nordic Shelf Supplies GmbH",
        "po_reference": "PO-5001",
        "currency": "EUR",
        "sku": "SKU-A",
        "quantity": "100",
        "unit_price": "20.00",
        "line_text": "SKU-A  Retail shelf bracket A  Qty 100  Unit EUR 20.00  Net EUR 2000.00",
    },
    {
        "invoice_id": "INV-1002",
        "supplier": "Nordic Shelf Supplies GmbH",
        "po_reference": "PO-5002",
        "currency": "EUR",
        "sku": "SKU-A",
        "quantity": "100",
        "unit_price": "20.00",
        "line_text": "SKU-A  Retail shelf bracket A  Qty 100  Unit EUR 20.00  Net EUR 2000.00",
    },
    {
        "invoice_id": "INV-1003",
        "supplier": "Nordic Shelf Supplies GmbH",
        "po_reference": "PO-5003",
        "currency": "EUR",
        "sku": "SKU-A",
        "quantity": "100",
        "unit_price": "20.00",
        "line_text": "SKU-A  Retail shelf bracket A  Qty 100  Unit EUR 20.00  Net EUR 2000.00",
    },
]

# Offline-only cases (no bundled PDF required for pytest).
OFFLINE_ONLY = [
    {
        "invoice_id": "INV-PRICE-1",
        "supplier": "Alpine Pack Co",
        "po_reference": "PO-9001",
        "currency": "EUR",
        "sku": "SKU-B",
        "quantity": "50",
        "unit_price": "12.00",
        "line_text": "SKU-B  Corrugated shipper B  Qty 50  Unit EUR 12.00  Net EUR 600.00",
        "page_number": 1,
    },
    {
        "invoice_id": "INV-MISSING-GR-1",
        "supplier": "Alpine Pack Co",
        "po_reference": "PO-9002",
        "currency": "EUR",
        "sku": "SKU-C",
        "quantity": "40",
        "unit_price": "5.00",
        "line_text": "SKU-C  Display card C  Qty 40  Unit EUR 5.00  Net EUR 200.00",
        "page_number": 1,
    },
]


def write_invoice_pdf(path: Path, invoice: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    c = canvas.Canvas(str(path), pagesize=A4)
    width, height = A4
    y = height - 72
    lines = [
        "SUPPLIER INVOICE",
        f"Invoice ID: {invoice['invoice_id']}",
        f"Supplier: {invoice['supplier']}",
        f"Purchase Order: {invoice['po_reference']}",
        f"Currency: {invoice['currency']} (net amounts)",
        "",
        "Line items:",
        invoice["line_text"],
        "",
        "Payment terms: Net 30. Do not pay without AP approval.",
    ]
    for text in lines:
        c.drawString(72, y, text)
        y -= 18
    c.showPage()
    c.save()


def write_extracted(invoice: dict, source_pdf: str | None, page_number: int = 1) -> None:
    EXTRACTED_DIR.mkdir(parents=True, exist_ok=True)
    payload = {
        "invoice_id": invoice["invoice_id"],
        "supplier": invoice["supplier"],
        "po_reference": invoice["po_reference"],
        "currency": invoice["currency"],
        "lines": [
            {
                "sku": invoice["sku"],
                "quantity": invoice["quantity"],
                "unit_price": invoice["unit_price"],
                "page_number": page_number,
                "supporting_text": invoice["line_text"],
            }
        ],
        "source_pdf": source_pdf,
        "extraction_mode": "offline_fixture",
    }
    out = EXTRACTED_DIR / f"{invoice['invoice_id']}.json"
    out.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    print(f"Wrote {out}")


def main() -> None:
    for invoice in INVOICES:
        pdf_name = f"{invoice['invoice_id']}.pdf"
        pdf_path = PDF_DIR / pdf_name
        write_invoice_pdf(pdf_path, invoice)
        print(f"Wrote {pdf_path}")
        write_extracted(invoice, source_pdf=f"invoices/{pdf_name}", page_number=1)

    for invoice in OFFLINE_ONLY:
        write_extracted(
            invoice,
            source_pdf=None,
            page_number=int(invoice.get("page_number", 1)),
        )


if __name__ == "__main__":
    main()
