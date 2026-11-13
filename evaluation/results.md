# Evaluation results

Generated: 2026-11-13 12:45 UTC

Only runs actually performed are listed. Cloud / live local ADK rows are added by those scripts when credentials are available.

| Run label | Invoice | Expected status | Actual status | Expected amount | Actual amount | Expected owner | Actual owner | Pass |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| offline rules | INV-1001 | MATCHED | MATCHED | 0.00 | 0.00 | AP Analyst | AP Analyst | yes |
| offline rules | INV-1002 | RECEIPT_DISCREPANCY | RECEIPT_DISCREPANCY | 400.00 | 400.00 | Receiving | Receiving | yes |
| offline rules | INV-1003 | DUPLICATE_SUSPECTED | DUPLICATE_SUSPECTED | — | — | Accounts Payable | Accounts Payable | yes |
| offline rules | INV-PRICE-1 | PRICE_DISCREPANCY | PRICE_DISCREPANCY | 100.00 | 100.00 | Purchasing | Purchasing | yes |
| offline rules | INV-MISSING-GR-1 | INSUFFICIENT_EVIDENCE | INSUFFICIENT_EVIDENCE | — | — | Accounts Payable | Accounts Payable | yes |

Notes from this build session:
- **offline rules**: measured via `pytest` + `scripts/run_eval.py` (pass).
- **live local ADK**: `adk web --port 8000 .` started successfully at http://127.0.0.1:8000 and loaded the agent package; full INV-1002 LLM turn was **not** measured here (no Gemini/Vertex credentials in the environment).
- **deployed cloud agent**: not measured (no `AGENT_ENGINE_RESOURCE_NAME` / GCP credentials).
