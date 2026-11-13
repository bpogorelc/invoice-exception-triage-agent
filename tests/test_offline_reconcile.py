"""Offline acceptance tests — no cloud credentials required."""

from __future__ import annotations

from decimal import Decimal

import pytest

from invoice_exception_triage_agent.extract import extract_pdf_text_by_page, read_invoice_document
from invoice_exception_triage_agent.models import (
    CaseStatus,
    ExtractedInvoice,
    InvestigationChecks,
    OwnerTeam,
    ReasonCode,
)
from invoice_exception_triage_agent.offline_pipeline import triage_invoice
from invoice_exception_triage_agent.reconcile import reconcile_case
from invoice_exception_triage_agent.data_store import list_invoice_pdfs


@pytest.mark.parametrize(
    ("invoice_id", "status", "reason", "amount", "owner"),
    [
        (
            "INV-1001",
            CaseStatus.MATCHED,
            ReasonCode.CLEAN_MATCH,
            Decimal("0.00"),
            OwnerTeam.ANALYST,
        ),
        (
            "INV-1002",
            CaseStatus.RECEIPT_DISCREPANCY,
            ReasonCode.QTY_RECEIVED_SHORT,
            Decimal("400.00"),
            OwnerTeam.RECEIVING,
        ),
        (
            "INV-1003",
            CaseStatus.DUPLICATE_SUSPECTED,
            ReasonCode.DUPLICATE_INVOICE_ID,
            None,
            OwnerTeam.ACCOUNTS_PAYABLE,
        ),
        (
            "INV-PRICE-1",
            CaseStatus.PRICE_DISCREPANCY,
            ReasonCode.UNIT_PRICE_MISMATCH,
            Decimal("100.00"),
            OwnerTeam.PURCHASING,
        ),
        (
            "INV-MISSING-GR-1",
            CaseStatus.INSUFFICIENT_EVIDENCE,
            ReasonCode.MISSING_GOODS_RECEIPT,
            None,
            OwnerTeam.ACCOUNTS_PAYABLE,
        ),
    ],
)
def test_fixture_routing(invoice_id, status, reason, amount, owner):
    result = triage_invoice(f"Review invoice {invoice_id}.")
    assert result.status == status
    assert result.reason_code == reason
    assert result.recommended_owner == owner
    assert result.payment_initiated is False
    if amount is None:
        assert result.disputed_amount_eur is None
    else:
        assert result.disputed_amount_eur == amount


def test_inv_1002_evidence_and_wording():
    result = triage_invoice("Review invoice INV-1002.")
    assert result.affected_sku == "SKU-A"
    assert result.source_refs.invoice_page == 1
    assert result.source_refs.po_line_id == "PO-5002-L1"
    assert result.source_refs.goods_receipt_id == "GR-8002"
    note = result.analyst_note.lower()
    assert "400" in result.analyst_note or "400.00" in result.analyst_note
    assert "receiving" in note
    assert "pending verification" in note
    # Must not frame €400 as savings or a confirmed overpayment.
    assert "not classified as savings" in note
    assert "confirmed overpayment" in note and "not classified" in note
    assert "is savings" not in note
    assert "is a confirmed overpayment" not in note
    assert result.payment_initiated is False


def test_missing_evidence_cannot_yield_matched():
    invoice = ExtractedInvoice.model_validate(
        {
            "invoice_id": "INV-1002",
            "supplier": "Nordic Shelf Supplies GmbH",
            "po_reference": "PO-5002",
            "currency": "EUR",
            "lines": [
                {
                    "sku": "SKU-A",
                    "quantity": "100",
                    "unit_price": "20.00",
                    "page_number": 1,
                    "supporting_text": "SKU-A",
                }
            ],
        }
    )
    outcome = reconcile_case(
        invoice,
        purchase_order=None,
        goods_receipt=None,
        ledger_hit=None,
        checks=InvestigationChecks(
            po_lookup_done=True,
            gr_lookup_done=True,
            duplicate_check_done=True,
        ),
    )
    assert outcome.status != CaseStatus.MATCHED
    assert outcome.status == CaseStatus.INSUFFICIENT_EVIDENCE


def test_incomplete_checks_cannot_yield_matched():
    result = triage_invoice("Review invoice INV-1001.", skip_lookups=True)
    assert result.status != CaseStatus.MATCHED
    assert result.reason_code == ReasonCode.CHECKS_INCOMPLETE


def test_pdf_text_is_searchable_for_demo_invoices():
    pdfs = list_invoice_pdfs()
    assert "INV-1002" in pdfs
    pages = extract_pdf_text_by_page(pdfs["INV-1002"])
    blob = "\n".join(text for _, text in pages)
    assert "INV-1002" in blob
    assert "PO-5002" in blob
    assert "SKU-A" in blob


def test_extraction_validates_with_pydantic():
    invoice = read_invoice_document("INV-1002", prefer_live_extraction=False)
    assert invoice.invoice_id == "INV-1002"
    assert invoice.po_reference == "PO-5002"
    assert invoice.lines[0].sku == "SKU-A"
    assert invoice.lines[0].page_number == 1
