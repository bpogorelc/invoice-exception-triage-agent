"""Credential-free offline triage used by pytest and evaluation tables."""

from __future__ import annotations

from typing import Any, Optional

from invoice_exception_triage_agent.extract import parse_invoice_id_from_message, read_invoice_document
from invoice_exception_triage_agent.models import (
    ExtractedInvoice,
    GoodsReceipt,
    InvestigationChecks,
    LedgerHit,
    PurchaseOrder,
    TriageResult,
)
from invoice_exception_triage_agent.reconcile import reconcile_case
from invoice_exception_triage_agent.route import finalize_triage
from invoice_exception_triage_agent.tools import run_required_lookups


def triage_invoice(
    message_or_invoice_id: str,
    *,
    extracted_invoice: Optional[ExtractedInvoice] = None,
    skip_lookups: bool = False,
) -> TriageResult:
    invoice_id = parse_invoice_id_from_message(message_or_invoice_id) or message_or_invoice_id.upper()
    invoice = extracted_invoice or read_invoice_document(invoice_id, prefer_live_extraction=False)

    state: dict[str, Any] = {
        "investigation_trace": [],
        "checks": {},
    }
    if skip_lookups:
        state["checks"] = InvestigationChecks().model_dump()
    else:
        sku = invoice.lines[0].sku if invoice.lines else None
        run_required_lookups(
            invoice_id=invoice.invoice_id or invoice_id,
            po_number=invoice.po_reference,
            sku=sku,
            state=state,
        )

    checks = InvestigationChecks.model_validate(state.get("checks") or {})
    purchase_order = (
        PurchaseOrder.model_validate(state["purchase_order"])
        if state.get("purchase_order")
        else None
    )
    goods_receipt = (
        GoodsReceipt.model_validate(state["goods_receipt"])
        if state.get("goods_receipt")
        else None
    )
    ledger_hit = (
        LedgerHit.model_validate(state["ledger_hit"]) if state.get("ledger_hit") else None
    )

    outcome = reconcile_case(
        invoice,
        purchase_order,
        goods_receipt,
        ledger_hit,
        checks,
        force_incomplete_checks=skip_lookups,
    )
    return finalize_triage(outcome, state.get("investigation_trace") or [])


def triage_to_dict(message_or_invoice_id: str, **kwargs: Any) -> dict[str, Any]:
    return triage_invoice(message_or_invoice_id, **kwargs).model_dump(mode="json")
