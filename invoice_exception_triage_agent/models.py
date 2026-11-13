"""Pydantic models for extraction, investigation, reconciliation and routing."""

from __future__ import annotations

from decimal import Decimal
from enum import Enum
from typing import Any, Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator


class Money(BaseModel):
    """EUR net amount stored as Decimal string for exact arithmetic."""

    model_config = ConfigDict(arbitrary_types_allowed=True)

    amount: Decimal
    currency: str = "EUR"

    @field_validator("amount", mode="before")
    @classmethod
    def _to_decimal(cls, value: Any) -> Decimal:
        if value is None or value == "":
            raise ValueError("amount is missing")
        return Decimal(str(value))


class InvoiceLine(BaseModel):
    sku: Optional[str] = None
    quantity: Optional[Decimal] = None
    unit_price: Optional[Decimal] = None
    page_number: Optional[int] = None
    supporting_text: Optional[str] = None

    @field_validator("quantity", "unit_price", mode="before")
    @classmethod
    def _optional_decimal(cls, value: Any) -> Optional[Decimal]:
        if value is None or value == "":
            return None
        return Decimal(str(value))


class ExtractedInvoice(BaseModel):
    invoice_id: Optional[str] = None
    supplier: Optional[str] = None
    po_reference: Optional[str] = None
    currency: Optional[str] = None
    lines: list[InvoiceLine] = Field(default_factory=list)
    source_pdf: Optional[str] = None
    extraction_mode: str = "offline_fixture"


class PurchaseOrderLine(BaseModel):
    line_id: str
    sku: str
    description: str = ""
    quantity: Decimal
    unit_price: Decimal
    currency: str = "EUR"

    @field_validator("quantity", "unit_price", mode="before")
    @classmethod
    def _to_decimal(cls, value: Any) -> Decimal:
        return Decimal(str(value))


class PurchaseOrder(BaseModel):
    po_number: str
    supplier: str
    currency: str = "EUR"
    lines: list[PurchaseOrderLine]


class GoodsReceiptLine(BaseModel):
    sku: str
    quantity_received: Decimal

    @field_validator("quantity_received", mode="before")
    @classmethod
    def _to_decimal(cls, value: Any) -> Decimal:
        return Decimal(str(value))


class GoodsReceipt(BaseModel):
    gr_id: str
    po_number: str
    lines: list[GoodsReceiptLine]


class LedgerHit(BaseModel):
    invoice_id: str
    exists: bool
    posted_status: Optional[str] = None
    note: Optional[str] = None


class ToolOutcome(str, Enum):
    FOUND = "found"
    NOT_FOUND = "not_found"
    ERROR = "error"


class TraceEntry(BaseModel):
    tool: str
    lookup_keys: dict[str, Any]
    outcome: ToolOutcome
    detail: Optional[str] = None


class InvestigationChecks(BaseModel):
    po_lookup_done: bool = False
    gr_lookup_done: bool = False
    duplicate_check_done: bool = False
    po_lookup_error: bool = False
    gr_lookup_error: bool = False
    duplicate_check_error: bool = False

    @property
    def all_required_complete(self) -> bool:
        return (
            self.po_lookup_done
            and self.gr_lookup_done
            and self.duplicate_check_done
            and not self.po_lookup_error
            and not self.gr_lookup_error
            and not self.duplicate_check_error
        )


class CaseStatus(str, Enum):
    MATCHED = "MATCHED"
    RECEIPT_DISCREPANCY = "RECEIPT_DISCREPANCY"
    PRICE_DISCREPANCY = "PRICE_DISCREPANCY"
    DUPLICATE_SUSPECTED = "DUPLICATE_SUSPECTED"
    INSUFFICIENT_EVIDENCE = "INSUFFICIENT_EVIDENCE"
    TECHNICAL_ERROR = "TECHNICAL_ERROR"


class ReasonCode(str, Enum):
    CLEAN_MATCH = "CLEAN_MATCH"
    QTY_RECEIVED_SHORT = "QTY_RECEIVED_SHORT"
    UNIT_PRICE_MISMATCH = "UNIT_PRICE_MISMATCH"
    DUPLICATE_INVOICE_ID = "DUPLICATE_INVOICE_ID"
    MISSING_PO = "MISSING_PO"
    MISSING_GOODS_RECEIPT = "MISSING_GOODS_RECEIPT"
    MISSING_INVOICE_FIELDS = "MISSING_INVOICE_FIELDS"
    CHECKS_INCOMPLETE = "CHECKS_INCOMPLETE"
    LOOKUP_FAILURE = "LOOKUP_FAILURE"


class OwnerTeam(str, Enum):
    RECEIVING = "Receiving"
    PURCHASING = "Purchasing"
    ACCOUNTS_PAYABLE = "Accounts Payable"
    ANALYST = "AP Analyst"


class SourceRefs(BaseModel):
    invoice_id: Optional[str] = None
    invoice_page: Optional[int] = None
    invoice_supporting_text: Optional[str] = None
    po_number: Optional[str] = None
    po_line_id: Optional[str] = None
    goods_receipt_id: Optional[str] = None


class TriageResult(BaseModel):
    status: CaseStatus
    reason_code: ReasonCode
    affected_sku: Optional[str] = None
    disputed_amount_eur: Optional[Decimal] = None
    source_refs: SourceRefs = Field(default_factory=SourceRefs)
    recommended_owner: OwnerTeam
    next_action: str
    analyst_note: str
    investigation_trace: list[TraceEntry] = Field(default_factory=list)
    payment_initiated: bool = False

    @field_validator("disputed_amount_eur", mode="before")
    @classmethod
    def _optional_decimal(cls, value: Any) -> Optional[Decimal]:
        if value is None or value == "":
            return None
        return Decimal(str(value))


class WorkflowState(BaseModel):
    """Typed ADK workflow state passed between nodes."""

    user_message: str = ""
    invoice_id_requested: Optional[str] = None
    extracted_invoice: Optional[dict[str, Any]] = None
    purchase_order: Optional[dict[str, Any]] = None
    goods_receipt: Optional[dict[str, Any]] = None
    ledger_hit: Optional[dict[str, Any]] = None
    checks: dict[str, Any] = Field(default_factory=dict)
    investigation_trace: list[dict[str, Any]] = Field(default_factory=list)
    triage_result: Optional[dict[str, Any]] = None
    analyst_note: str = ""
