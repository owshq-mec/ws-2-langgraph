# Incident Response Runbook

**Version:** 3.0
**Owner:** team-platform
**Audience:** All engineers with on-call responsibility.

This runbook is the playbook for handling production incidents in the DataOps Knowledge Hub. Read it once before your first on-call shift. Reference it during incidents.

---

## 1. Severity Classification

Classify within the first 5 minutes. **When in doubt, classify up** — it's easier to downgrade than to play catch-up.

| Sev | Description | Examples |
|-----|-------------|----------|
| **P1** | Customer-facing outage or data loss in progress | API 5xx > 50%; revenue pipeline failed and dashboards blank; PII exposure |
| **P2** | Significant degradation, no immediate customer impact | One pipeline failed but others compensating; latency 2-5× normal |
| **P3** | Functional issue, low urgency | Slow query; one stale partition; isolated bad data |
| **P4** | Cosmetic / informational | Misleading log message; a chart label is wrong |

## 2. The First 15 Minutes (P1/P2)

1. **Acknowledge the page.** This stops escalation timers.
2. **Open an incident channel.** Slack: `#inc-YYYYMMDD-<short-name>`. Pin the channel.
3. **Declare an Incident Commander.** Usually the first responder. The IC coordinates; they do **not** debug.
4. **Post the initial status.** Template:
   > **Sev:** P1
   > **What:** `etl_billing_daily` failed at 03:14 BRT, dashboards stale.
   > **Customer impact:** Revenue Overview dashboard blank for ~200 users.
   > **IC:** @alice  |  **Comms:** @bob  |  **Tech lead:** @carol
   > **Status page:** Updating.
5. **Notify stakeholders** for P1: update the public status page, post in `#leadership`, page the on-call EM.

## 3. Communication Channels

| Audience | Channel | Cadence during incident |
|----------|---------|--------------------------|
| Engineering | `#inc-*` channel | Continuous |
| Leadership | `#leadership` | Every 30 minutes |
| Customers | Public status page (statuspage.io) | At declaration, at mitigation, at resolution |
| Affected internal users | Owning team channel (`#billing-eng`, etc.) | At declaration and resolution |

## 4. Rollback Procedures

Roll back **before** debugging when customer impact is active.

| Component | Rollback action | Owner |
|-----------|-----------------|-------|
| API deployment | `railway rollback <previous-id>` | team-platform |
| Pipeline code | Revert PR in Airflow repo, redeploy DAG | owning team |
| Database migration | Run down-migration; if not safe, restore from latest snapshot | team-platform |
| Schema change in Postgres | `pg_restore` from last nightly backup | team-platform |
| Bad data already written | Stop downstream pipelines, re-run from last good watermark | owning team |

## 5. Post-Mortem Template

Required for **every P1 and P2**, due within 5 business days. Use this template — start a Notion page in `/Incidents/`:

```
# Incident YYYY-MM-DD — <short name>

## Summary
1–2 sentences: what happened, who was affected, how long.

## Timeline (BRT)
- HH:MM — first signal
- HH:MM — page fired
- HH:MM — IC declared
- HH:MM — root cause hypothesis
- HH:MM — mitigation applied
- HH:MM — resolved

## Impact
- Customers affected:
- Revenue impact:
- Data loss / quality damage:

## Root Cause
Why did this happen? Go 3–5 levels deep with "but why?"

## What Went Well
- …

## What Went Poorly
- …

## Action Items
| # | Action | Owner | Due | Linear |
|---|--------|-------|-----|--------|
| 1 | …     | …    | …   | …     |
```

## 6. After the Incident

1. Mark the incident resolved in PagerDuty and on the status page.
2. Schedule the post-mortem within 48 hours.
3. **Blameless culture:** the goal is system improvement, not individual accountability.
4. Track action items in Linear with the `incident-followup` label.
