"""ADK Workflow: read → investigate → ensure lookups → reconcile → route."""

from __future__ import annotations

import json
from typing import Any

from google.adk import Agent
from google.adk.workflow import START, Workflow, node

from invoice_exception_triage_agent.config import get_settings
from invoice_exception_triage_agent.extract import parse_invoice_id_from_message, read_invoice_document
from invoice_exception_triage_agent.models import (
    ExtractedInvoice,
    GoodsReceipt,
    InvestigationChecks,
    LedgerHit,
    PurchaseOrder,
    WorkflowState,
)
from invoice_exception_triage_agent.reconcile import reconcile_case
from invoice_exception_triage_agent.route import finalize_triage
from invoice_exception_triage_agent.tools import (
    check_invoice_in_ledger,
    lookup_goods_received,
    lookup_purchase_order,
)

settings = get_settings()


@node
def read_document(ctx: Any, node_input: str) -> dict[str, Any]:
    """Extract and validate the supplier invoice referenced by the analyst."""
    message = node_input if isinstance(node_input, str) else str(node_input)
    invoice_id = parse_invoice_id_from_message(message)
    if not invoice_id:
        raise ValueError("Please include an invoice id such as INV-1002 in your request.")

    prefer_live = settings.has_credentials
    invoice = read_invoice_document(invoice_id, prefer_live_extraction=prefer_live)
    payload = invoice.model_dump(mode="json")

    ctx.state["user_message"] = message
    ctx.state["invoice_id_requested"] = invoice_id
    ctx.state["extracted_invoice"] = payload
    ctx.state["investigation_trace"] = []
    ctx.state["checks"] = InvestigationChecks().model_dump()
    ctx.state["purchase_order"] = None
    ctx.state["goods_receipt"] = None
    ctx.state["ledger_hit"] = None
    ctx.state["triage_result"] = None
    ctx.state["analyst_note"] = ""
    return payload


investigate_agent = Agent(
    name="investigate",
    model=settings.model_name,
    description="Read-only investigator for AP invoice exceptions.",
    instruction=(
        "You investigate retail AP invoice exceptions. "
        "You already have an extracted invoice in the conversation context from the prior step. "
        "Use only these read-only tools as needed for the case:\n"
        "1) lookup_purchase_order(po_number)\n"
        "2) lookup_goods_received(po_number, sku)\n"
        "3) check_invoice_in_ledger(invoice_id)\n"
        "Always run all three lookups when the extracted invoice provides the keys. "
        "If a PO reference or SKU is missing, still attempt the ledger duplicate check. "
        "Do not approve payment. Do not invent records. "
        "After tools finish, briefly list which lookups you ran and their outcomes."
    ),
    tools=[lookup_purchase_order, lookup_goods_received, check_invoice_in_ledger],
)


@node
def ensure_required_lookups(ctx: Any, node_input: Any = None) -> dict[str, Any]:
    """Guarantee PO, GR and ledger checks exist even if the LLM skipped a tool."""
    invoice = ExtractedInvoice.model_validate(ctx.state.get("extracted_invoice") or {})
    checks = InvestigationChecks.model_validate(ctx.state.get("checks") or {})
    sku = invoice.lines[0].sku if invoice.lines else None
    invoice_id = invoice.invoice_id or ctx.state.get("invoice_id_requested")

    class _Ctx:
        def __init__(self, state: dict[str, Any]) -> None:
            self.state = state

    bucket: dict[str, Any] = {
        "investigation_trace": list(ctx.state.get("investigation_trace") or []),
        "checks": checks.model_dump(),
        "purchase_order": ctx.state.get("purchase_order"),
        "goods_receipt": ctx.state.get("goods_receipt"),
        "ledger_hit": ctx.state.get("ledger_hit"),
    }
    tool_ctx = _Ctx(bucket)

    # Fill only missing required lookups so MATCHED never rides on skipped tools.
    if not checks.po_lookup_done:
        lookup_purchase_order(invoice.po_reference or "", tool_context=tool_ctx)  # type: ignore[arg-type]
        checks = InvestigationChecks.model_validate(bucket.get("checks") or {})

    if not checks.gr_lookup_done:
        lookup_goods_received(
            invoice.po_reference or "",
            sku or "",
            tool_context=tool_ctx,  # type: ignore[arg-type]
        )
        checks = InvestigationChecks.model_validate(bucket.get("checks") or {})

    if not checks.duplicate_check_done:
        check_invoice_in_ledger(invoice_id or "", tool_context=tool_ctx)  # type: ignore[arg-type]

    ctx.state["investigation_trace"] = bucket.get("investigation_trace") or []
    ctx.state["checks"] = bucket.get("checks") or {}
    ctx.state["purchase_order"] = bucket.get("purchase_order")
    ctx.state["goods_receipt"] = bucket.get("goods_receipt")
    ctx.state["ledger_hit"] = bucket.get("ledger_hit")
    return {
        "checks": ctx.state["checks"],
        "trace_count": len(ctx.state["investigation_trace"] or []),
    }


@node
def reconcile(ctx: Any, node_input: Any = None) -> dict[str, Any]:
    """Deterministic Decimal reconciliation; never initiates payment."""
    invoice = ExtractedInvoice.model_validate(ctx.state.get("extracted_invoice") or {})
    checks = InvestigationChecks.model_validate(ctx.state.get("checks") or {})
    purchase_order = (
        PurchaseOrder.model_validate(ctx.state["purchase_order"])
        if ctx.state.get("purchase_order")
        else None
    )
    goods_receipt = (
        GoodsReceipt.model_validate(ctx.state["goods_receipt"])
        if ctx.state.get("goods_receipt")
        else None
    )
    ledger_hit = (
        LedgerHit.model_validate(ctx.state["ledger_hit"]) if ctx.state.get("ledger_hit") else None
    )
    outcome = reconcile_case(invoice, purchase_order, goods_receipt, ledger_hit, checks)
    ctx.state["temp:reconcile_status"] = outcome.status.value
    ctx.state["temp:reconcile_reason"] = outcome.reason_code.value
    # Stash serializable outcome pieces for the next node.
    ctx.state["temp:reconcile_blob"] = {
        "status": outcome.status.value,
        "reason_code": outcome.reason_code.value,
        "affected_sku": outcome.affected_sku,
        "disputed_amount_eur": (
            str(outcome.disputed_amount_eur) if outcome.disputed_amount_eur is not None else None
        ),
        "source_refs": outcome.source_refs.model_dump(mode="json"),
        "facts": outcome.facts,
    }
    return ctx.state["temp:reconcile_blob"]


@node
def route_and_explain(ctx: Any, node_input: Any = None) -> str:
    """Produce structured triage result and a short analyst-facing note."""
    from invoice_exception_triage_agent.models import CaseStatus, ReasonCode, SourceRefs
    from invoice_exception_triage_agent.reconcile import ReconcileOutcome

    blob = ctx.state.get("temp:reconcile_blob") or node_input or {}
    if isinstance(blob, str):
        blob = json.loads(blob)
    outcome = ReconcileOutcome(
        status=CaseStatus(blob["status"]),
        reason_code=ReasonCode(blob["reason_code"]),
        affected_sku=blob.get("affected_sku"),
        disputed_amount_eur=blob.get("disputed_amount_eur"),
        source_refs=SourceRefs.model_validate(blob.get("source_refs") or {}),
        facts=blob.get("facts") or {},
    )
    result = finalize_triage(outcome, ctx.state.get("investigation_trace") or [])
    payload = result.model_dump(mode="json")
    ctx.state["triage_result"] = payload
    ctx.state["analyst_note"] = result.analyst_note

    pretty = json.dumps(payload, indent=2)
    return (
        f"{result.analyst_note}\n\n"
        f"--- structured result ---\n{pretty}\n\n"
        "Reminder: the analyst retains approval authority; this agent never initiates payment."
    )


# When credentials are missing, keep a deterministic workflow usable for import/smoke.
# The investigate LLM node still requires a model at runtime for `adk web` / `adk run`.
root_agent = Workflow(
    name="invoice_exception_triage",
    description=(
        "Invoice Exception Triage Agent for retail AP. "
        "Ask: Review invoice INV-1002."
    ),
    state_schema=WorkflowState,
    edges=[
        (
            START,
            read_document,
            investigate_agent,
            ensure_required_lookups,
            reconcile,
            route_and_explain,
        )
    ],
)


def _strip_model_for_offline_import() -> None:
    """No-op helper referenced by tests to document offline vs live paths."""
    return None


__all__ = ["root_agent", "read_document", "investigate_agent", "ensure_required_lookups"]
