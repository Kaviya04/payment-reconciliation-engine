# Payment Reconciliation Engine

Automated billing reconciliation tool that matches invoices against incoming transactions, flags discrepancies, and exports structured reports for finance teams.

Built to mirror real-world workflows in billing & payments operations — the kind of daily work in accounts receivable, partner finance, and settlement teams.

---

## What it does

Loads invoice and transaction data, runs SQL-based reconciliation logic in-memory (SQLite), and classifies every record into one of five categories:

| Status | Meaning |
|---|---|
| `MATCHED` | Invoice and transaction amounts agree |
| `AMOUNT_MISMATCH` | Transaction exists but amount differs |
| `UNMATCHED_INVOICE` | Invoice issued — no payment received |
| `ORPHAN_TRANSACTION` | Payment received — no matching invoice |
| `DUPLICATE_PAYMENT` | Same invoice paid more than once |

Outputs a full Excel report with one tab per category, plus a partner-level outstanding balance summary.

---

## Sample output

```
============================================================
  RECONCILIATION REPORT — 2026-06-23
============================================================

  ✓  Matched invoices       : 6
  ⚠  Amount mismatches      : 2
  ✗  Unmatched invoices     : 5
  ?  Orphan transactions    : 1
  !!  Duplicate payments    : 1

  Total discrepancy (€)    : 1,450.75
  Total outstanding (€)    : 6,200.75
```

---

## Project structure

```
payment-reconciliation-engine/
├── data/
│   ├── invoices.csv          # Invoice master data
│   └── transactions.csv      # Incoming payment transactions
├── sql/
│   └── reconciliation_queries.sql   # Core SQL logic (standalone reference)
├── output/
│   └── reconciliation_report_YYYY-MM-DD.xlsx
└── payment_reconciliation.py
```

---

## Setup

```bash
pip install pandas openpyxl
python payment_reconciliation.py
```

---

## SQL logic

The reconciliation is built on five SQL patterns:

```sql
-- Unmatched invoices (core of AR follow-up)
SELECT i.*
FROM invoices i
LEFT JOIN transactions t ON i.invoice_id = t.invoice_id
WHERE t.txn_id IS NULL;

-- Amount mismatches (partial payments, FX rounding)
SELECT i.invoice_id, i.amount AS invoiced, t.amount AS received,
       ROUND(i.amount - t.amount, 2) AS discrepancy
FROM invoices i
INNER JOIN transactions t ON i.invoice_id = t.invoice_id
WHERE ROUND(i.amount, 2) != ROUND(t.amount, 2);

-- Duplicate payments
SELECT invoice_id, COUNT(*) AS txn_count
FROM transactions
GROUP BY invoice_id
HAVING COUNT(*) > 1;
```

Full query set in `/sql/reconciliation_queries.sql`.

---

## Skills demonstrated

- SQL: JOINs, GROUP BY, HAVING, CASE WHEN, NULL handling, aggregations
- Python: pandas, SQLite, data pipeline design, Excel export
- Finance domain: accounts receivable, payment matching, open items management

---

## Extending this

- Connect to a real database (PostgreSQL, Snowflake) by swapping SQLite for SQLAlchemy
- Schedule daily runs via cron or Airflow
- Add email alerts when discrepancies exceed a threshold
- Build a dashboard layer on top (Tableau, Metabase, or Streamlit)
