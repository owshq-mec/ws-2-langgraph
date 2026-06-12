# Pipeline SLA Definitions

**Version:** 1.4
**Owner:** team-platform
**Last reviewed:** 2026-Q1

This document is the source of truth for pipeline SLAs. Monitoring (`Pipeline Monitor` dashboard) and on-call rotation pages use these targets as alert thresholds.

---

## 1. SLA Targets

| Pipeline | Owner | Schedule | Uptime | Max latency | Freshness |
|----------|-------|----------|--------|-------------|-----------|
| `etl_billing_daily` | team-billing | `0 3 * * *` | **99.9%** | 45 min | < 24h |
| `etl_orders_hourly` | team-billing | `0 * * * *` | **99.5%** | 15 min | < 1h |
| `etl_customer_sync` | team-platform | `0 6 * * *` | **99.0%** | 30 min | < 24h |
| `analytics_revenue_agg` | team-analytics | `0 5 * * *` | **99.5%** | 60 min | < 24h |

**Uptime** is measured as `(successful runs / scheduled runs)` over a rolling 30-day window.
**Latency** is `pipeline end time − pipeline scheduled start time`. Breaches over the latency threshold count as failures for the uptime calculation.
**Freshness** is the max age of data visible to downstream consumers.

## 2. Severity Levels

| Sev | Trigger | First-response target | Channel |
|-----|---------|------------------------|---------|
| **P1** | `etl_billing_daily` or `etl_orders_hourly` failed; revenue dashboard stale > 4h; customer-visible impact | **15 min** | PagerDuty → on-call → `#incidents` |
| **P2** | Any pipeline latency breach; non-revenue pipeline failed; degraded but not down | **1 hour** | PagerDuty (business hours) → `#incidents` |
| **P3** | Slow runs trending toward SLA breach; partial data quality issues | **Next business day** | `#platform-eng` |
| **P4** | Cosmetic issues, low-priority enhancements | Best effort | Linear ticket |

## 3. Escalation

1. **Primary on-call** (owning team) — paged immediately on P1/P2.
2. **Secondary on-call** — paged if primary unacknowledged in 10 minutes.
3. **Engineering Manager** — paged if P1 unresolved in 30 minutes.
4. **VP Engineering** — paged if P1 unresolved in 90 minutes or customer-facing > 1h.

Rotations are managed in PagerDuty. The current on-call for each team is visible in the `#oncall-now` Slack channel.

## 4. Reporting

- **Weekly:** Pipeline reliability report posted to `#platform-eng` every Monday 09:00 BRT.
- **Monthly:** SLA scorecard reviewed in the cross-team data ops sync (last Friday of the month).
- **Quarterly:** This document reviewed and adjusted based on observed performance and business needs.

## 5. Exceptions

Planned maintenance windows do **not** count against uptime, provided they are announced in `#platform-eng` at least 24 hours in advance and are < 4 hours in duration.
