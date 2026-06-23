-- ============================================================
-- payment_reconciliation.sql
-- Core SQL logic for billing reconciliation
-- ============================================================

-- 1. MATCHED: invoices with a transaction where amounts agree
SELECT
    i.invoice_id,
    i.partner,
    i.amount          AS invoiced_amount,
    t.txn_id,
    t.amount          AS received_amount,
    t.txn_date,
    t.channel,
    'MATCHED'         AS recon_status
FROM invoices i
INNER JOIN transactions t ON i.invoice_id = t.invoice_id
WHERE ROUND(i.amount, 2) = ROUND(t.amount, 2);

-- ============================================================

-- 2. AMOUNT MISMATCH: transaction exists but amounts differ
SELECT
    i.invoice_id,
    i.partner,
    i.amount              AS invoiced_amount,
    t.txn_id,
    t.amount              AS received_amount,
    ROUND(i.amount - t.amount, 2) AS discrepancy,
    t.txn_date,
    'AMOUNT_MISMATCH'     AS recon_status
FROM invoices i
INNER JOIN transactions t ON i.invoice_id = t.invoice_id
WHERE ROUND(i.amount, 2) != ROUND(t.amount, 2)
   OR t.amount IS NULL;

-- ============================================================

-- 3. UNMATCHED INVOICES: billed but no payment received
SELECT
    i.invoice_id,
    i.partner,
    i.amount          AS invoiced_amount,
    i.due_date,
    i.status,
    NULL              AS txn_id,
    NULL              AS received_amount,
    'UNMATCHED_INVOICE' AS recon_status
FROM invoices i
LEFT JOIN transactions t ON i.invoice_id = t.invoice_id
WHERE t.txn_id IS NULL;

-- ============================================================

-- 4. ORPHAN TRANSACTIONS: payment received with no matching invoice
SELECT
    t.txn_id,
    t.invoice_id      AS referenced_invoice,
    t.partner,
    t.amount          AS received_amount,
    t.txn_date,
    t.reference,
    'ORPHAN_TRANSACTION' AS recon_status
FROM transactions t
LEFT JOIN invoices i ON t.invoice_id = i.invoice_id
WHERE i.invoice_id IS NULL;

-- ============================================================

-- 5. DUPLICATE TRANSACTIONS: same invoice paid more than once
SELECT
    invoice_id,
    partner,
    COUNT(*)          AS txn_count,
    SUM(amount)       AS total_received,
    'DUPLICATE_PAYMENT' AS recon_status
FROM transactions
GROUP BY invoice_id
HAVING COUNT(*) > 1;

-- ============================================================

-- 6. SUMMARY: outstanding balance by partner
SELECT
    i.partner,
    COUNT(*)                                        AS total_invoices,
    SUM(i.amount)                                   AS total_billed,
    SUM(CASE WHEN i.status = 'paid' THEN i.amount ELSE 0 END)   AS total_paid,
    SUM(CASE WHEN i.status != 'paid' THEN i.amount ELSE 0 END)  AS total_outstanding
FROM invoices i
GROUP BY i.partner
ORDER BY total_outstanding DESC;
