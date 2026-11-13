"""Local JSON fixture accessors (synthetic ERP stand-ins)."""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Any, Optional

from invoice_exception_triage_agent.config import get_settings
from invoice_exception_triage_agent.models import GoodsReceipt, LedgerHit, PurchaseOrder


def _fixtures_dir() -> Path:
    return Path(get_settings().fixtures_dir)


@lru_cache
def _load_json(name: str) -> dict[str, Any]:
    path = _fixtures_dir() / name
    with path.open(encoding="utf-8") as handle:
        return json.load(handle)


def clear_cache() -> None:
    _load_json.cache_clear()


def get_purchase_order(po_number: str) -> Optional[PurchaseOrder]:
    data = _load_json("purchase_orders.json")
    raw = data.get(po_number)
    if raw is None:
        return None
    return PurchaseOrder.model_validate(raw)


def get_goods_receipt_for_po_sku(po_number: str, sku: str) -> Optional[GoodsReceipt]:
    data = _load_json("goods_receipts.json")
    raw = data.get(po_number)
    if raw is None:
        return None
    receipt = GoodsReceipt.model_validate(raw)
    matching = [line for line in receipt.lines if line.sku == sku]
    if not matching:
        return None
    return GoodsReceipt(gr_id=receipt.gr_id, po_number=receipt.po_number, lines=matching)


def check_ledger_invoice(invoice_id: str) -> LedgerHit:
    data = _load_json("ledger.json")
    raw = data.get(invoice_id)
    if raw is None:
        return LedgerHit(invoice_id=invoice_id, exists=False)
    return LedgerHit.model_validate(raw)


def list_invoice_pdfs() -> dict[str, Path]:
    invoice_dir = _fixtures_dir() / "invoices"
    return {path.stem: path for path in invoice_dir.glob("*.pdf")}


def load_extracted_fixture(invoice_id: str) -> Optional[dict[str, Any]]:
    path = _fixtures_dir() / "extracted" / f"{invoice_id}.json"
    if not path.exists():
        return None
    with path.open(encoding="utf-8") as handle:
        return json.load(handle)
