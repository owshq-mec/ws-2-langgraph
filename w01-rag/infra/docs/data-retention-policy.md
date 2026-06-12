# Data Retention Policy

**Version:** 2.1
**Owner:** Data Governance Council
**Last reviewed:** 2026-Q1
**Applies to:** All production data systems in the DataOps Knowledge Hub.

---

## 1. Purpose

This policy defines how long each class of data is retained, when it must be deleted, and which team is accountable. Retention is bounded by two forces: business utility (analytics, audit, customer service) and legal obligation (LGPD, tax law, contractual minimums). Where the two conflict, **legal minimums always win**.

## 2. Data Classifications

| Class | Examples | Retention | Storage Tier |
|-------|----------|-----------|--------------|
| **PII (Personal)** | `customers.name`, `customers.email`, IP addresses in logs | **90 days** after account closure | Encrypted at rest |
| **Transactional** | `orders.*`, payment records, invoices | **7 years** (Brazilian tax law) | Hot for 12 months, cold archive after |
| **Operational logs** | Application logs, API access logs | **30 days** | Hot only |
| **Pipeline metadata** | DAG runs, task durations, lineage events | **180 days** | Hot for 30 days, warm after |
| **Aggregated analytics** | `fact_revenue`, dashboard snapshots | **Indefinite** (no PII) | Warm tier |
| **Backups** | Postgres / Mongo daily snapshots | **35 days** (rolling) | Cold storage |

## 3. Deletion Procedures

PII deletion follows the **right-to-erasure** workflow defined in LGPD Art. 18:

1. Customer (or authorized agent) submits request via `dpo@company.com`.
2. Request acknowledged within 5 business days.
3. Deletion executed within 15 business days, covering:
   - PostgreSQL: `customers`, `orders` (PII columns nulled, FK integrity preserved)
   - MongoDB: events tagged with `customer_id`
   - Qdrant: vector embeddings derived from PII documents
   - SeaweedFS: any uploaded customer documents
4. Confirmation issued in writing.

Transactional rows are **never hard-deleted** before the 7-year window — instead, PII fields are anonymized in place.

## 4. Compliance — LGPD (Lei nº 13.709/2018)

- **Lawful basis** for retention: legitimate interest (analytics), contract performance (orders), legal obligation (tax records).
- **Data subject rights** honored: access, rectification, deletion, portability, objection.
- **DPO contact:** `dpo@company.com` — published in the privacy notice.
- **Audit trail:** every deletion request is logged in MongoDB `events.dpo_requests` with timestamp, operator, and affected record counts.

## 5. Responsible Teams

| Concern | Team | Slack |
|---------|------|-------|
| Policy ownership & review | Data Governance Council | `#data-governance` |
| Postgres PII deletion | team-platform | `#platform-eng` |
| Pipeline data retention | team-billing | `#billing-eng` |
| Backup lifecycle | team-platform | `#platform-eng` |
| Analytics tables (no PII) | team-analytics | `#analytics` |
| DPO escalations | Legal | `#legal-privacy` |

## 6. Review

This policy is reviewed every six months, or immediately following any regulatory change, incident affecting personal data, or material change to the data architecture.
