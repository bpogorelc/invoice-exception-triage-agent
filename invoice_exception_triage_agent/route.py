"""Route exceptions and draft an analyst-facing note from validated facts only."""

from __future__ import annotations

from decimal import Decimal
from typing import Any, Optional

from invoice_exception_triage_agent.models import (
    CaseStatus,
    OwnerTeam,
    TraceEntry,
    TriageResult,
)
from invoice_exception_triage_agent.reconcile import ReconcileOutcome


def _fmt_eur(amount: Optional[Decimal]) -> Optional[str]:
    if amount is None:
        return None
    return f"EUR {amount.quantize(Decimal('0.01'))}"


def build_analyst_note(outcome: ReconcileOutcome) -> str:
    refs = outcome.source_refs
    facts = outcome.facts
    amount = _fmt_eur(outcome.disputed_amount_eur)

    if outcome.status == CaseStatus.MATCHED:
        return (
            f"Invoice {refs.invoice_id} matches PO {refs.po_number} line {refs.po_line_id} "
            f"and goods receipt {refs.goods_receipt_id} for {outcome.affected_sku} "
            f"(qty {facts.get('invoice_quantity')} at EUR {facts.get('unit_price')} net). "
            "Ready for analyst approval. Payment is not initiated by this agent."
        )

    if outcome.status == CaseStatus.RECEIPT_DISCREPANCY:
        return (
            f"Invoice {refs.invoice_id} (page {refs.invoice_page}) bills "
            f"{facts.get('invoice_quantity')} units of {outcome.affected_sku} at "
            f"EUR {facts.get('unit_price')} net, matching PO {refs.po_number} line "
            f"{refs.po_line_id}. Goods receipt {refs.goods_receipt_id} records only "
            f"{facts.get('received_quantity')} units received "
            f"({facts.get('quantity_delta')} units / {amount} pending verification). "
            "Ask Receiving to confirm whether the remaining units arrived. "
            "This amount is not classified as savings or a confirmed overpayment. "
            "Payment is not initiated by this agent."
        )

    if outcome.status == CaseStatus.PRICE_DISCREPANCY:
        return (
            f"Invoice {refs.invoice_id} prices {outcome.affected_sku} at "
            f"EUR {facts.get('invoice_unit_price')} vs PO {refs.po_number} line "
            f"{refs.po_line_id} at EUR {facts.get('po_unit_price')} "
            f"(qty {facts.get('invoice_quantity')}; disputed {amount}). "
            "Route to Purchasing for price confirmation. Payment is not initiated by this agent."
        )

    if outcome.status == CaseStatus.DUPLICATE_SUSPECTED:
        return (
            f"Invoice ID {refs.invoice_id} already exists in the AP ledger "
            f"({facts.get('ledger_status')}: {facts.get('ledger_note')}). "
            "Route to Accounts Payable to investigate a suspected duplicate. "
            "Payment is not initiated by this agent."
        )

    if outcome.status == CaseStatus.TECHNICAL_ERROR:
        return (
            f"Technical lookup failure while reviewing invoice {refs.invoice_id}. "
            f"{facts.get('detail')}. Payment is not initiated by this agent."
        )

    return (
        f"Insufficient evidence to clear invoice {refs.invoice_id} "
        f"({outcome.reason_code.value}: {facts.get('detail')}). "
        "Payment is not initiated by this agent."
    )


def route_outcome(outcome: ReconcileOutcome) -> tuple[OwnerTeam, str]:
    if outcome.status == CaseStatus.MATCHED:
        return OwnerTeam.ANALYST, "Approve for payment processing if policy checks pass."
    if outcome.status == CaseStatus.RECEIPT_DISCREPANCY:
        return (
            OwnerTeam.RECEIVING,
            "Confirm whether the remaining units arrived and update the goods receipt.",
        )
    if outcome.status == CaseStatus.PRICE_DISCREPANCY:
        return OwnerTeam.PURCHASING, "Confirm contracted unit price with the supplier or buyer."
    if outcome.status == CaseStatus.DUPLICATE_SUSPECTED:
        return OwnerTeam.ACCOUNTS_PAYABLE, "Investigate suspected duplicate invoice ID in the ledger."
    if outcome.status == CaseStatus.TECHNICAL_ERROR:
        return OwnerTeam.ACCOUNTS_PAYABLE, "Retry lookups or escalate the technical failure."
    return OwnerTeam.ACCOUNTS_PAYABLE, "Gather missing evidence before any approval decision."


def finalize_triage(
    outcome: ReconcileOutcome,
    investigation_trace: list[TraceEntry] | list[dict[str, Any]],
) -> TriageResult:
    owner, next_action = route_outcome(outcome)
    note = build_analyst_note(outcome)
    trace_models = [
        item if isinstance(item, TraceEntry) else TraceEntry.model_validate(item)
        for item in investigation_trace
    ]
    return TriageResult(
        status=outcome.status,
        reason_code=outcome.reason_code,
        affected_sku=outcome.affected_sku,
        disputed_amount_eur=outcome.disputed_amount_eur,
        source_refs=outcome.source_refs,
        recommended_owner=owner,
        next_action=next_action,
        analyst_note=note,
        investigation_trace=trace_models,
        payment_initiated=False,
    )
