"""Narrow read-only investigation tools for the ADK agent."""

from __future__ import annotations

from typing import Any, Optional

from google.adk.tools import ToolContext

from invoice_exception_triage_agent import data_store
from invoice_exception_triage_agent.models import InvestigationChecks, ToolOutcome, TraceEntry


def _get_state(tool_context: Optional[ToolContext]) -> Any:
    if tool_context is None:
        return {}
    return tool_context.state


def _append_trace(state: Any, entry: TraceEntry) -> None:
    trace = list(state.get("investigation_trace") or [])
    trace.append(entry.model_dump(mode="json"))
    state["investigation_trace"] = trace


def _update_checks(state: Any, **flags: bool) -> None:
    checks = InvestigationChecks.model_validate(state.get("checks") or {})
    for key, value in flags.items():
        setattr(checks, key, value)
    state["checks"] = checks.model_dump()


def lookup_purchase_order(po_number: str, tool_context: ToolContext | None = None) -> dict[str, Any]:
    """Look up a purchase order by PO number. Read-only synthetic ERP lookup."""
    state = _get_state(tool_context)
    keys = {"po_number": po_number}
    try:
        po = data_store.get_purchase_order(po_number)
        if po is None:
            _append_trace(
                state,
                TraceEntry(
                    tool="lookup_purchase_order",
                    lookup_keys=keys,
                    outcome=ToolOutcome.NOT_FOUND,
                    detail="No PO record",
                ),
            )
            _update_checks(state, po_lookup_done=True, po_lookup_error=False)
            state["purchase_order"] = None
            return {"status": "not_found", "po_number": po_number}
        payload = po.model_dump(mode="json")
        state["purchase_order"] = payload
        _append_trace(
            state,
            TraceEntry(
                tool="lookup_purchase_order",
                lookup_keys=keys,
                outcome=ToolOutcome.FOUND,
                detail=f"Found {po.po_number} with {len(po.lines)} line(s)",
            ),
        )
        _update_checks(state, po_lookup_done=True, po_lookup_error=False)
        return {"status": "found", "purchase_order": payload}
    except Exception as exc:  # noqa: BLE001 - surface as technical lookup failure
        _append_trace(
            state,
            TraceEntry(
                tool="lookup_purchase_order",
                lookup_keys=keys,
                outcome=ToolOutcome.ERROR,
                detail=str(exc),
            ),
        )
        _update_checks(state, po_lookup_done=True, po_lookup_error=True)
        return {"status": "error", "error": str(exc), "po_number": po_number}


def lookup_goods_received(
    po_number: str, sku: str, tool_context: ToolContext | None = None
) -> dict[str, Any]:
    """Look up goods received for a purchase order and SKU. Read-only."""
    state = _get_state(tool_context)
    keys = {"po_number": po_number, "sku": sku}
    try:
        receipt = data_store.get_goods_receipt_for_po_sku(po_number, sku)
        if receipt is None:
            _append_trace(
                state,
                TraceEntry(
                    tool="lookup_goods_received",
                    lookup_keys=keys,
                    outcome=ToolOutcome.NOT_FOUND,
                    detail="No goods receipt for PO/SKU",
                ),
            )
            _update_checks(state, gr_lookup_done=True, gr_lookup_error=False)
            state["goods_receipt"] = None
            return {"status": "not_found", "po_number": po_number, "sku": sku}
        payload = receipt.model_dump(mode="json")
        state["goods_receipt"] = payload
        _append_trace(
            state,
            TraceEntry(
                tool="lookup_goods_received",
                lookup_keys=keys,
                outcome=ToolOutcome.FOUND,
                detail=f"Found {receipt.gr_id}",
            ),
        )
        _update_checks(state, gr_lookup_done=True, gr_lookup_error=False)
        return {"status": "found", "goods_receipt": payload}
    except Exception as exc:  # noqa: BLE001
        _append_trace(
            state,
            TraceEntry(
                tool="lookup_goods_received",
                lookup_keys=keys,
                outcome=ToolOutcome.ERROR,
                detail=str(exc),
            ),
        )
        _update_checks(state, gr_lookup_done=True, gr_lookup_error=True)
        return {"status": "error", "error": str(exc), **keys}


def check_invoice_in_ledger(
    invoice_id: str, tool_context: ToolContext | None = None
) -> dict[str, Any]:
    """Check whether a supplier invoice ID already exists in the AP ledger."""
    state = _get_state(tool_context)
    keys = {"invoice_id": invoice_id}
    try:
        hit = data_store.check_ledger_invoice(invoice_id)
        payload = hit.model_dump(mode="json")
        state["ledger_hit"] = payload
        outcome = ToolOutcome.FOUND if hit.exists else ToolOutcome.NOT_FOUND
        _append_trace(
            state,
            TraceEntry(
                tool="check_invoice_in_ledger",
                lookup_keys=keys,
                outcome=outcome,
                detail=hit.note or ("exists" if hit.exists else "not in ledger"),
            ),
        )
        _update_checks(state, duplicate_check_done=True, duplicate_check_error=False)
        return {"status": "found" if hit.exists else "not_found", "ledger_hit": payload}
    except Exception as exc:  # noqa: BLE001
        _append_trace(
            state,
            TraceEntry(
                tool="check_invoice_in_ledger",
                lookup_keys=keys,
                outcome=ToolOutcome.ERROR,
                detail=str(exc),
            ),
        )
        _update_checks(state, duplicate_check_done=True, duplicate_check_error=True)
        return {"status": "error", "error": str(exc), "invoice_id": invoice_id}


def run_required_lookups(
    *,
    invoice_id: str,
    po_number: Optional[str],
    sku: Optional[str],
    state: Optional[dict[str, Any]] = None,
) -> dict[str, Any]:
    """Deterministic offline investigation that records the same trace shape as tools."""
    bucket = state if state is not None else {}
    if po_number:
        lookup_purchase_order(po_number, tool_context=type("Ctx", (), {"state": bucket})())
    else:
        _update_checks(bucket, po_lookup_done=True, po_lookup_error=False)
        _append_trace(
            bucket,
            TraceEntry(
                tool="lookup_purchase_order",
                lookup_keys={"po_number": None},
                outcome=ToolOutcome.NOT_FOUND,
                detail="Invoice missing PO reference",
            ),
        )
        bucket["purchase_order"] = None

    if po_number and sku:
        lookup_goods_received(po_number, sku, tool_context=type("Ctx", (), {"state": bucket})())
    else:
        _update_checks(bucket, gr_lookup_done=True, gr_lookup_error=False)
        _append_trace(
            bucket,
            TraceEntry(
                tool="lookup_goods_received",
                lookup_keys={"po_number": po_number, "sku": sku},
                outcome=ToolOutcome.NOT_FOUND,
                detail="Missing PO or SKU for goods receipt lookup",
            ),
        )
        bucket["goods_receipt"] = None

    check_invoice_in_ledger(invoice_id, tool_context=type("Ctx", (), {"state": bucket})())
    return bucket
