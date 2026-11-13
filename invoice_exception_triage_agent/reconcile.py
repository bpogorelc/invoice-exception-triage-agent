"""Deterministic EUR net reconciliation using Decimal exact matching by SKU."""

from __future__ import annotations

from decimal import Decimal
from typing import Any, Optional

from invoice_exception_triage_agent.models import (
    CaseStatus,
    ExtractedInvoice,
    GoodsReceipt,
    InvestigationChecks,
    LedgerHit,
    PurchaseOrder,
    ReasonCode,
    SourceRefs,
    TraceEntry,
)


class ReconcileOutcome:
    def __init__(
        self,
        *,
        status: CaseStatus,
        reason_code: ReasonCode,
        affected_sku: Optional[str],
        disputed_amount_eur: Optional[Decimal],
        source_refs: SourceRefs,
        facts: dict[str, Any],
    ) -> None:
        self.status = status
        self.reason_code = reason_code
        self.affected_sku = affected_sku
        self.disputed_amount_eur = disputed_amount_eur
        self.source_refs = source_refs
        self.facts = facts


def _line_by_sku(po: PurchaseOrder, sku: str):
    for line in po.lines:
        if line.sku == sku:
            return line
    return None


def reconcile_case(
    invoice: ExtractedInvoice,
    purchase_order: Optional[PurchaseOrder],
    goods_receipt: Optional[GoodsReceipt],
    ledger_hit: Optional[LedgerHit],
    checks: InvestigationChecks,
    *,
    force_incomplete_checks: bool = False,
) -> ReconcileOutcome:
    """Reconcile invoice vs PO vs GR.

    Rules:
    - Missing record => INSUFFICIENT_EVIDENCE (never MATCHED)
    - Lookup/technical failure => TECHNICAL_ERROR (never MATCHED)
    - Incomplete required checks => cannot MATCHED
    - Exact EUR net matching by SKU only
    """
    inv_line = invoice.lines[0] if invoice.lines else None
    sku = inv_line.sku if inv_line else None
    page = inv_line.page_number if inv_line else None
    supporting = inv_line.supporting_text if inv_line else None

    refs = SourceRefs(
        invoice_id=invoice.invoice_id,
        invoice_page=page,
        invoice_supporting_text=supporting,
        po_number=invoice.po_reference,
    )

    if checks.po_lookup_error or checks.gr_lookup_error or checks.duplicate_check_error:
        return ReconcileOutcome(
            status=CaseStatus.TECHNICAL_ERROR,
            reason_code=ReasonCode.LOOKUP_FAILURE,
            affected_sku=sku,
            disputed_amount_eur=None,
            source_refs=refs,
            facts={"detail": "One or more lookups failed technically"},
        )

    checks_complete = checks.all_required_complete and not force_incomplete_checks
    if not checks_complete:
        return ReconcileOutcome(
            status=CaseStatus.INSUFFICIENT_EVIDENCE,
            reason_code=ReasonCode.CHECKS_INCOMPLETE,
            affected_sku=sku,
            disputed_amount_eur=None,
            source_refs=refs,
            facts={"detail": "Required PO, goods receipt and ledger checks were not all completed"},
        )

    if ledger_hit and ledger_hit.exists:
        return ReconcileOutcome(
            status=CaseStatus.DUPLICATE_SUSPECTED,
            reason_code=ReasonCode.DUPLICATE_INVOICE_ID,
            affected_sku=sku,
            disputed_amount_eur=None,
            source_refs=refs,
            facts={
                "ledger_status": ledger_hit.posted_status,
                "ledger_note": ledger_hit.note,
            },
        )

    if (
        not invoice.invoice_id
        or not invoice.po_reference
        or not invoice.currency
        or inv_line is None
        or inv_line.sku is None
        or inv_line.quantity is None
        or inv_line.unit_price is None
    ):
        return ReconcileOutcome(
            status=CaseStatus.INSUFFICIENT_EVIDENCE,
            reason_code=ReasonCode.MISSING_INVOICE_FIELDS,
            affected_sku=sku,
            disputed_amount_eur=None,
            source_refs=refs,
            facts={"detail": "Invoice extraction is missing required fields"},
        )

    if invoice.currency.upper() != "EUR":
        return ReconcileOutcome(
            status=CaseStatus.INSUFFICIENT_EVIDENCE,
            reason_code=ReasonCode.MISSING_INVOICE_FIELDS,
            affected_sku=sku,
            disputed_amount_eur=None,
            source_refs=refs,
            facts={"detail": "MVP supports EUR net amounts only"},
        )

    if purchase_order is None:
        return ReconcileOutcome(
            status=CaseStatus.INSUFFICIENT_EVIDENCE,
            reason_code=ReasonCode.MISSING_PO,
            affected_sku=sku,
            disputed_amount_eur=None,
            source_refs=refs,
            facts={"detail": "Purchase order not found"},
        )

    refs.po_number = purchase_order.po_number
    po_line = _line_by_sku(purchase_order, inv_line.sku)
    if po_line is None:
        return ReconcileOutcome(
            status=CaseStatus.INSUFFICIENT_EVIDENCE,
            reason_code=ReasonCode.MISSING_PO,
            affected_sku=sku,
            disputed_amount_eur=None,
            source_refs=refs,
            facts={"detail": f"No PO line for SKU {inv_line.sku}"},
        )
    refs.po_line_id = po_line.line_id

    if goods_receipt is None or not goods_receipt.lines:
        return ReconcileOutcome(
            status=CaseStatus.INSUFFICIENT_EVIDENCE,
            reason_code=ReasonCode.MISSING_GOODS_RECEIPT,
            affected_sku=sku,
            disputed_amount_eur=None,
            source_refs=refs,
            facts={"detail": "Goods receipt not found for PO/SKU"},
        )

    refs.goods_receipt_id = goods_receipt.gr_id
    gr_qty = goods_receipt.lines[0].quantity_received
    inv_qty = inv_line.quantity
    inv_price = inv_line.unit_price
    po_price = po_line.unit_price

    if inv_price != po_price:
        disputed = (inv_price - po_price) * inv_qty
        return ReconcileOutcome(
            status=CaseStatus.PRICE_DISCREPANCY,
            reason_code=ReasonCode.UNIT_PRICE_MISMATCH,
            affected_sku=sku,
            disputed_amount_eur=disputed,
            source_refs=refs,
            facts={
                "invoice_unit_price": str(inv_price),
                "po_unit_price": str(po_price),
                "invoice_quantity": str(inv_qty),
            },
        )

    if inv_qty != gr_qty:
        qty_delta = inv_qty - gr_qty
        disputed = qty_delta * inv_price
        return ReconcileOutcome(
            status=CaseStatus.RECEIPT_DISCREPANCY,
            reason_code=ReasonCode.QTY_RECEIVED_SHORT,
            affected_sku=sku,
            disputed_amount_eur=disputed,
            source_refs=refs,
            facts={
                "invoice_quantity": str(inv_qty),
                "received_quantity": str(gr_qty),
                "quantity_delta": str(qty_delta),
                "unit_price": str(inv_price),
                "po_ordered_quantity": str(po_line.quantity),
            },
        )

    if inv_qty != po_line.quantity:
        return ReconcileOutcome(
            status=CaseStatus.INSUFFICIENT_EVIDENCE,
            reason_code=ReasonCode.CHECKS_INCOMPLETE,
            affected_sku=sku,
            disputed_amount_eur=None,
            source_refs=refs,
            facts={
                "detail": "Invoice quantity does not equal PO ordered quantity",
                "invoice_quantity": str(inv_qty),
                "po_quantity": str(po_line.quantity),
            },
        )

    return ReconcileOutcome(
        status=CaseStatus.MATCHED,
        reason_code=ReasonCode.CLEAN_MATCH,
        affected_sku=sku,
        disputed_amount_eur=Decimal("0.00"),
        source_refs=refs,
        facts={
            "invoice_quantity": str(inv_qty),
            "received_quantity": str(gr_qty),
            "unit_price": str(inv_price),
        },
    )


def parse_trace(raw_trace: list[dict[str, Any]] | None) -> list[TraceEntry]:
    return [TraceEntry.model_validate(item) for item in (raw_trace or [])]
