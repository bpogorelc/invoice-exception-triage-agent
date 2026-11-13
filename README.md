# Invoice Exception Triage Agent

Retail accounts-payable teams lose time chasing invoice exceptions across PDFs, purchase orders and goods receipts. This project shows an AP analyst asking **“Review invoice INV-1002.”** and receiving a concise recommendation with evidence and an owner — while retaining approval authority. The agent never initiates payment. All data is synthetic.

**Memorable case:** PO-5002 orders 100 × SKU-A at €20. INV-1002 bills all 100, but goods receipt GR-8002 records only 80. The agent reports a **receipt discrepancy of 20 units (€400 pending verification)**, cites invoice page 1 / PO line PO-5002-L1 / GR-8002, and asks **Receiving** to confirm whether the remaining 20 units arrived. The €400 is not described as savings or a confirmed overpayment.

## Architecture

```text
Analyst message
      │
      ▼
┌─────────────┐   PDF text + Gemini structured output (Pydantic)
│ Read doc    │───────────────────────────────────────────────┐
└─────────────┘                                               │
      │                                                       ▼
      ▼                                              ExtractedInvoice
┌─────────────┐   tools: PO / GR / ledger (read-only)
│ Investigate │───────────────────────────────────────────────┐
│  (ADK LLM)  │   shared Workflow state + tool trace          │
└─────────────┘                                               │
      │                                                       ▼
      ▼                                              typed lookup results
┌─────────────┐   Decimal exact match by SKU (EUR net)
│ Ensure +    │
│ Reconcile   │
└─────────────┘
      │
      ▼
┌─────────────┐   status, reason, amount, owner, analyst note
│ Route +     │
│ Explain     │
└─────────────┘
```

Stack: **Python 3.12**, **Google ADK 2.x Workflow**, **Gemini on Google Cloud**, **Pydantic**. Fixtures are local JSON + searchable PDFs (no custom UI, DB, OCR service or ERP).

## 90-second demo script

1. Run offline tests (no credentials): `.\.venv\Scripts\python.exe -m pytest`
2. (Optional once) `.\.venv\Scripts\adk.exe telemetry disable`
3. Start ADK web UI from the repo root: `.\.venv\Scripts\adk.exe web --port 8000 .`
4. Open http://127.0.0.1:8000, select `invoice_exception_triage_agent`.
5. Send: `Review invoice INV-1002.`
6. In the Events / trace panel, confirm tool calls: `lookup_purchase_order` (PO-5002), `lookup_goods_received` (PO-5002, SKU-A), `check_invoice_in_ledger` (INV-1002).
7. Read the note: 20 units / €400 pending verification → owner Receiving. Approve remains with the analyst.

Also try `INV-1001` (clean match) and `INV-1003` (suspected duplicate → Accounts Payable).

## Setup

```powershell
# Python 3.11+ required (this repo was verified with 3.12)
c:\users\bogdan\.local\bin\python3.12.exe -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
python scripts\generate_fixtures.py
copy .env.example .env   # fill only for live/cloud runs
```

### Local verification (no credentials)

| Command | Purpose |
| --- | --- |
| `python -m pytest` | Offline acceptance tests |
| `python scripts\run_eval.py` | Writes `evaluation/results.md` |

### Live local ADK (credentials required)

Set Vertex project/region/model or an AI Studio key in `.env`, then:

```powershell
.\.venv\Scripts\adk.exe telemetry disable
.\.venv\Scripts\adk.exe web --port 8000 .
# or CLI chat:
.\.venv\Scripts\adk.exe run invoice_exception_triage_agent
```

Inspect tool calls in the ADK Web Events panel (tool name, lookup keys, outcomes). The workflow also stores `investigation_trace` on session state.

**Local verification** = pytest + offline eval. **Cloud verification** = deploy + remote smoke below.

### Deploy to Google Cloud Agent Runtime

Documented path: official `adk deploy agent_engine` (Agent Runtime / formerly Vertex AI Agent Engine). See the [Agent Runtime ADK quickstart](https://docs.cloud.google.com/gemini-enterprise-agent-platform/build/runtime/quickstart-adk).

```powershell
gcloud auth application-default login
# Enable Vertex AI API for the project, then:
python scripts\deploy_agent_runtime.py
# Copy the reasoningEngine resource name into .env as AGENT_ENGINE_RESOURCE_NAME
python scripts\smoke_remote.py
python scripts\cleanup_remote.py
```

Fixtures ship inside `invoice_exception_triage_agent/fixtures/` so the remote package can resolve synthetic PO/GR/ledger data.

### Optional: Gemini Enterprise registration

Registering the deployed agent with Gemini Enterprise is optional and not required for this demo. The offline tests, ADK web UI and Agent Runtime smoke path work independently of that integration.

## Evaluation table

See [`evaluation/results.md`](evaluation/results.md) after `python scripts\run_eval.py`. Rows are labeled `offline rules`, `live local ADK` or `deployed cloud agent` and only include measurements from runs actually performed.

## Project layout

```text
invoice_exception_triage_agent/
  agent.py            # ADK Workflow root_agent
  extract.py          # PDF text + Gemini structured output
  tools.py            # PO / GR / ledger lookups + trace
  reconcile.py        # Decimal reconciliation
  route.py            # owner + analyst note
  fixtures/           # PDFs, extracted JSON, PO/GR/ledger
scripts/              # fixtures, eval, deploy, smoke, cleanup
tests/                # offline acceptance tests
```
