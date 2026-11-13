"""Run offline evaluation and append a small expected-vs-actual table."""

from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from invoice_exception_triage_agent.offline_pipeline import triage_invoice  # noqa: E402

OUT_DIR = ROOT / "evaluation"
OUT_MD = OUT_DIR / "results.md"
OUT_JSON = OUT_DIR / "latest_offline.json"

CASES = [
    {
        "invoice_id": "INV-1001",
        "expected_status": "MATCHED",
        "expected_reason": "CLEAN_MATCH",
        "expected_amount": "0.00",
        "expected_owner": "AP Analyst",
    },
    {
        "invoice_id": "INV-1002",
        "expected_status": "RECEIPT_DISCREPANCY",
        "expected_reason": "QTY_RECEIVED_SHORT",
        "expected_amount": "400.00",
        "expected_owner": "Receiving",
    },
    {
        "invoice_id": "INV-1003",
        "expected_status": "DUPLICATE_SUSPECTED",
        "expected_reason": "DUPLICATE_INVOICE_ID",
        "expected_amount": None,
        "expected_owner": "Accounts Payable",
    },
    {
        "invoice_id": "INV-PRICE-1",
        "expected_status": "PRICE_DISCREPANCY",
        "expected_reason": "UNIT_PRICE_MISMATCH",
        "expected_amount": "100.00",
        "expected_owner": "Purchasing",
    },
    {
        "invoice_id": "INV-MISSING-GR-1",
        "expected_status": "INSUFFICIENT_EVIDENCE",
        "expected_reason": "MISSING_GOODS_RECEIPT",
        "expected_amount": None,
        "expected_owner": "Accounts Payable",
    },
]


def _amount_str(value) -> str:
    if value is None:
        return "—"
    return str(Decimal(str(value)).quantize(Decimal("0.01")))


def main() -> int:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    rows = []
    for case in CASES:
        result = triage_invoice(f"Review invoice {case['invoice_id']}.")
        actual_amount = (
            None if result.disputed_amount_eur is None else str(result.disputed_amount_eur)
        )
        ok = (
            result.status.value == case["expected_status"]
            and result.reason_code.value == case["expected_reason"]
            and result.recommended_owner.value == case["expected_owner"]
            and _amount_str(actual_amount) == _amount_str(case["expected_amount"])
        )
        rows.append(
            {
                "run_label": "offline rules",
                "invoice_id": case["invoice_id"],
                "expected_status": case["expected_status"],
                "actual_status": result.status.value,
                "expected_reason": case["expected_reason"],
                "actual_reason": result.reason_code.value,
                "expected_amount": _amount_str(case["expected_amount"]),
                "actual_amount": _amount_str(actual_amount),
                "expected_owner": case["expected_owner"],
                "actual_owner": result.recommended_owner.value,
                "pass": ok,
            }
        )

    stamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    lines = [
        f"# Evaluation results",
        "",
        f"Generated: {stamp}",
        "",
        "Only runs actually performed are listed. Cloud / live local ADK rows are added by those scripts when credentials are available.",
        "",
        "| Run label | Invoice | Expected status | Actual status | Expected amount | Actual amount | Expected owner | Actual owner | Pass |",
        "| --- | --- | --- | --- | --- | --- | --- | --- | --- |",
    ]
    for row in rows:
        lines.append(
            f"| {row['run_label']} | {row['invoice_id']} | {row['expected_status']} | "
            f"{row['actual_status']} | {row['expected_amount']} | {row['actual_amount']} | "
            f"{row['expected_owner']} | {row['actual_owner']} | {'yes' if row['pass'] else 'NO'} |"
        )
    lines.append("")
    OUT_MD.write_text("\n".join(lines), encoding="utf-8")
    OUT_JSON.write_text(json.dumps(rows, indent=2), encoding="utf-8")
    print(OUT_MD.read_text(encoding="utf-8"))
    return 0 if all(r["pass"] for r in rows) else 1


if __name__ == "__main__":
    raise SystemExit(main())
