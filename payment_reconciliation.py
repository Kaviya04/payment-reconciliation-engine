"""
payment_reconciliation.py
=========================
Automated payment reconciliation engine for billing operations.

Loads invoice and transaction data into SQLite, runs reconciliation
logic, flags discrepancies, and exports a structured report.
"""

import sqlite3
import pandas as pd
from datetime import date
import os

DATA_DIR = os.path.join(os.path.dirname(__file__), "data")
OUTPUT_DIR = os.path.join(os.path.dirname(__file__), "output")
os.makedirs(OUTPUT_DIR, exist_ok=True)


# ── 1. Load CSVs into SQLite ─────────────────────────────────────────────────

def load_data(conn: sqlite3.Connection) -> tuple[pd.DataFrame, pd.DataFrame]:
    invoices = pd.read_csv(os.path.join(DATA_DIR, "invoices.csv"))
    transactions = pd.read_csv(os.path.join(DATA_DIR, "transactions.csv"))

    invoices.to_sql("invoices", conn, if_exists="replace", index=False)
    transactions.to_sql("transactions", conn, if_exists="replace", index=False)

    print(f"  Loaded {len(invoices)} invoices, {len(transactions)} transactions")
    return invoices, transactions


# ── 2. Reconciliation queries ─────────────────────────────────────────────────

def run_reconciliation(conn: sqlite3.Connection) -> dict[str, pd.DataFrame]:

    matched = pd.read_sql_query("""
        SELECT
            i.invoice_id, i.partner,
            i.amount    AS invoiced_amount,
            t.txn_id,
            t.amount    AS received_amount,
            t.txn_date, t.channel,
            'MATCHED'   AS recon_status
        FROM invoices i
        INNER JOIN transactions t ON i.invoice_id = t.invoice_id
        WHERE ROUND(COALESCE(i.amount, 0), 2) = ROUND(COALESCE(t.amount, 0), 2)
    """, conn)

    amount_mismatch = pd.read_sql_query("""
        SELECT
            i.invoice_id, i.partner,
            i.amount                        AS invoiced_amount,
            t.txn_id,
            t.amount                        AS received_amount,
            ROUND(i.amount - COALESCE(t.amount, 0), 2) AS discrepancy,
            t.txn_date,
            'AMOUNT_MISMATCH'               AS recon_status
        FROM invoices i
        INNER JOIN transactions t ON i.invoice_id = t.invoice_id
        WHERE ROUND(COALESCE(i.amount, 0), 2) != ROUND(COALESCE(t.amount, 0), 2)
           OR t.amount IS NULL
    """, conn)

    unmatched_invoices = pd.read_sql_query("""
        SELECT
            i.invoice_id, i.partner,
            i.amount    AS invoiced_amount,
            i.due_date, i.status,
            NULL        AS txn_id,
            NULL        AS received_amount,
            'UNMATCHED_INVOICE' AS recon_status
        FROM invoices i
        LEFT JOIN transactions t ON i.invoice_id = t.invoice_id
        WHERE t.txn_id IS NULL
    """, conn)

    orphan_transactions = pd.read_sql_query("""
        SELECT
            t.txn_id,
            t.invoice_id    AS referenced_invoice,
            t.partner,
            t.amount        AS received_amount,
            t.txn_date, t.reference,
            'ORPHAN_TRANSACTION' AS recon_status
        FROM transactions t
        LEFT JOIN invoices i ON t.invoice_id = i.invoice_id
        WHERE i.invoice_id IS NULL
    """, conn)

    duplicate_payments = pd.read_sql_query("""
        SELECT
            invoice_id, partner,
            COUNT(*)    AS txn_count,
            SUM(amount) AS total_received,
            'DUPLICATE_PAYMENT' AS recon_status
        FROM transactions
        GROUP BY invoice_id
        HAVING COUNT(*) > 1
    """, conn)

    partner_summary = pd.read_sql_query("""
        SELECT
            partner,
            COUNT(*)                                                    AS total_invoices,
            ROUND(SUM(amount), 2)                                       AS total_billed,
            ROUND(SUM(CASE WHEN status = 'paid' THEN amount ELSE 0 END), 2)  AS total_paid,
            ROUND(SUM(CASE WHEN status != 'paid' THEN amount ELSE 0 END), 2) AS total_outstanding
        FROM invoices
        GROUP BY partner
        ORDER BY total_outstanding DESC
    """, conn)

    return {
        "matched": matched,
        "amount_mismatch": amount_mismatch,
        "unmatched_invoices": unmatched_invoices,
        "orphan_transactions": orphan_transactions,
        "duplicate_payments": duplicate_payments,
        "partner_summary": partner_summary,
    }


# ── 3. Print summary to console ───────────────────────────────────────────────

def print_summary(results: dict[str, pd.DataFrame]) -> None:
    print("\n" + "="*60)
    print("  RECONCILIATION REPORT")
    print(f"  Run date: {date.today()}")
    print("="*60)

    print(f"\n  ✓  Matched invoices       : {len(results['matched'])}")
    print(f"  ⚠  Amount mismatches      : {len(results['amount_mismatch'])}")
    print(f"  ✗  Unmatched invoices     : {len(results['unmatched_invoices'])}")
    print(f"  ?  Orphan transactions    : {len(results['orphan_transactions'])}")
    print(f"  !!  Duplicate payments    : {len(results['duplicate_payments'])}")

    total_discrepancy = results["amount_mismatch"]["discrepancy"].sum() if not results["amount_mismatch"].empty else 0
    total_outstanding = results["partner_summary"]["total_outstanding"].sum()

    print(f"\n  Total discrepancy (€)    : {total_discrepancy:,.2f}")
    print(f"  Total outstanding (€)    : {total_outstanding:,.2f}")

    if not results["amount_mismatch"].empty:
        print("\n  ── Amount mismatches ──")
        print(results["amount_mismatch"][["invoice_id","partner","invoiced_amount","received_amount","discrepancy"]].to_string(index=False))

    if not results["unmatched_invoices"].empty:
        print("\n  ── Unmatched invoices (no payment received) ──")
        print(results["unmatched_invoices"][["invoice_id","partner","invoiced_amount","due_date","status"]].to_string(index=False))

    if not results["orphan_transactions"].empty:
        print("\n  ── Orphan transactions (no matching invoice) ──")
        print(results["orphan_transactions"][["txn_id","referenced_invoice","partner","received_amount"]].to_string(index=False))

    if not results["duplicate_payments"].empty:
        print("\n  ── Duplicate payments ──")
        print(results["duplicate_payments"].to_string(index=False))

    print("\n  ── Outstanding balance by partner ──")
    print(results["partner_summary"].to_string(index=False))
    print("\n" + "="*60)


# ── 4. Export to Excel ────────────────────────────────────────────────────────

def export_report(results: dict[str, pd.DataFrame]) -> None:
    output_path = os.path.join(OUTPUT_DIR, f"reconciliation_report_{date.today()}.xlsx")

    with pd.ExcelWriter(output_path, engine="openpyxl") as writer:
        for sheet_name, df in results.items():
            df.to_excel(writer, sheet_name=sheet_name, index=False)

    print(f"\n  Report saved → {output_path}")


# ── 5. Main ───────────────────────────────────────────────────────────────────

def main():
    print("\nPayment Reconciliation Engine")
    print("Loading data...")

    conn = sqlite3.connect(":memory:")

    try:
        load_data(conn)
        results = run_reconciliation(conn)
        print_summary(results)
        export_report(results)
    finally:
        conn.close()


if __name__ == "__main__":
    main()
