# Multi-Tenant Billing Platform — Design Document

**Author:** Satya Ramesh Koppisetti  
**Status:** For external / principal review  
**Scope:** Assignment-scale implementation (single deployable stack)

---

## 1. What was given

We were given a **failure scenario**, not a codebase to reverse-engineer.

**Inputs:**

- **Log excerpt (11 seconds, 03:17:38–49):** billing latency rising, connection pool exhausted, ingest slowing to multi-second delays and 504s, Redis timeouts on invoice generation, eventual 503 across tenants.
- **API surface:** ingest usage events, calculate billing totals (Rating), generate invoices (Billing).
- **Multi-tenant context:** several tenants with different profiles (SLA customer doing month-end billing, standard tenants, high-volume backfill ingest).
- **Expectation:** propose and implement a design that prevents this cascade, with evidence (tests + runnable system).

**What we did not have:** access to the original production system. Analysis is based on **observable symptoms** and standard billing-platform patterns, not forensic reconstruction of legacy code.

---

## 2. What we understood the problem to be

### 2.1 Core issue

The platform treated **all workloads as equal** on **shared resources** (Postgres pool, Redis, workers). Under month-end load, that produced a **two-phase cascade**:

| Phase | What failed | Symptom in logs |
|-------|-------------|-----------------|
| **1 — Rating** (`billing/calculate`) | Postgres connection pool | Pool exhausted; ingest blocked; 504/500 |
| **2 — Billing** (`invoices/generate`) | Redis (job enqueue path) | Redis timeout; 503 |

**Phase 1** is a **hold-time / concurrency** problem, not primarily a requests-per-second problem. A few long-running analytical queries can occupy every pool slot while fast ingest waits behind them.

**Phase 2** is a **secondary cascade**: components blocked waiting on the DB still hold Redis connections, so invoice orchestration cannot enqueue work even though generate itself is lightweight.

### 2.2 Key diagnostic clue

**One tenant’s ingest stayed fast (~14ms) throughout** while others degraded. That indicates **noisy-neighbor contention on a shared pool**, not a global outage from ingest volume alone.

### 2.3 Root cause (design-level statement)

> **Rating (heavy DB reads) and Billing (orchestration + external side effects) share infrastructure without isolation, backpressure, or workload-class separation.**

Contributing factors we designed against:

- Long-held DB connections on billing aggregation (no effective concurrency cap).
- Ingest coupled to DB availability on the hot path.
- No fast vs slow path separation.
- Single Redis role for both control-plane ops and durable queues.
- Slow failure modes (504/500) instead of fast rejection (429).

---

## 3. What we built (solution summary)

| Problem | Solution |
|---------|----------|
| Ingest lost or blocked when DB saturated | **Async ingest:** accept → durable queue → 202; workers persist later |
| Pool exhausted by billing | **Per-tenant concurrency limits** on slow paths; **429** when full |
| Slow billing queries | **Indexed reads + pre-aggregated daily usage**; query timeout |
| Generate blocked when DB/Redis degraded | **Async generate:** enqueue only in API; worker finalizes invoice |
| Redis cascade | **Split Redis:** ops (limits, semaphores) vs queue (streams) |
| One tenant starves others | **Separate worker pools** + **fair scheduling** across tenant queues |
| No ops levers | **Shedding** (pause backfill first), admin pause/resume, runbook |
| Double charge on retries | **Idempotent invoice finalization** (worker + DB rules) |

### 3.1 Three main flows

**Ingest (fast path)**  
Client sends event → validated and queued → **202**. No DB on the request path. Workers batch-write to Postgres.

**Calculate / Rating (slow path, synchronous)**  
Client sends billing period + invoice id → admission (rate + concurrency) → sum usage for that tenant and period → return **200** with total. Invoice row stored as **calculated**.

**Generate / Billing (async)**  
Client sends same invoice id → job queued → **202**. Worker marks invoice **generated** and triggers payment/notify side effects once.

**Relationship:** Events are tied to billing by **tenant + time range**, not by invoice id at ingest time. The **invoice id** links calculate and generate to the same bill.

---

## 4. Architecture (high level)

```
Clients
   │
   ▼
API Layer (admission: rate limits + concurrency on slow paths)
   │
   ├── Ingest ──────────► Event queues (Redis Streams) ──► Realtime / Backfill workers ──► Postgres (events + daily aggregates)
   │
   ├── Calculate ───────► Postgres (read aggregates / events) ──► Invoice row (calculated)
   │
   └── Generate ────────► Billing job queue ──► Billing workers ──► Invoice (generated) + external notify

Control plane: Redis (ops) — token buckets, semaphores, shedding signals  
Data plane queues: Redis (queue) — durable streams, AOF  
Observability: health + admin status + runbook
```

**Tenants:** configured tiers (SLA, standard, backfill) with different concurrency, rate, and scheduler weight.

---

## 5. Scope

### In scope (delivered)

- Multi-tenant ingest, calculate, generate, invoice status read
- Queue durability, deduplicated events, deferred worker ACK
- Pool protection via semaphores and fail-fast 429
- Daily usage aggregates for scalable Rating
- Split Redis, three worker pools, shedding FSM
- Admin kill switches and runbook
- Tests focused on **failure modes** (cascade, durability, idempotency, overflow)
- Postman collection for manual E2E

### Out of scope (explicit)

- Tiered / complex pricing engine
- Kafka-scale distributed ingestion
- Multi-region deployment
- Webhooks (polling only for invoice status)
- Full line-item invoice breakdown
- Production-grade PEL reclaim loop (documented as follow-up)

---

## 6. Design choices and tradeoffs

| Choice | Why | Tradeoff |
|--------|-----|----------|
| **Queue-based ingest (202)** | Durability decoupled from DB; ingest survives pool pressure | Usage visible for calculate only after worker flush (~seconds) |
| **Semaphore on billing, not ingest** | Protects pool **occupancy** (hold time), not just arrival rate | Legitimate billing requests get 429 at capacity |
| **Calculate synchronous, generate async** | Caller needs total immediately; generate has external I/O and strict idempotency | Generate requires polling; API may still enqueue duplicate jobs (worker no-ops if already finalized) |
| **Daily aggregates** | Rating reads small rollup rows instead of scanning all events | Brief window before aggregates exist; fallback to event scan |
| **Split Redis** | Ops traffic cannot starve durable queues during cascade | Two Redis instances to operate |
| **Three worker pools + fair scheduler** | Backfill cannot monopolize realtime/billing consumers | Fixed pool sizes need tuning |
| **429 on overload** | Predictable client backoff vs 504 after long waits | Clients must retry responsibly |
| **Shedding: backfill first** | Preserves SLA ingest and billing orchestration longest | Automated degradation may need manual reset |
| **Redis Streams (not Kafka)** | Sufficient for assignment scope; simpler to run end-to-end | At very large scale, a distributed log is the usual evolution |

### Alternatives we rejected

- **Rate limiting alone** — does not cap concurrent long-held DB slots.
- **Scaling Redis only** — does not fix pool hold time or tenant isolation.
- **Sync generate in API** — holds resources during outages; matches Phase 2 failure pattern.
- **Single shared worker pool with priorities** — priorities break under saturation.

---

## 7. How we validated the design

- **Automated tests** reproduce overload, queue durability, idempotency, and shedding — not happy-path-only checks.
- **Manual E2E:** ingest → wait for flush → calculate → generate → poll invoice status.
- **Operational docs:** runbook for month-end billing and cascade triage.

Success criteria for review: under simulated billing saturation, ingest still accepts **202**, overload returns **429** (not **500/504**), and duplicate invoice generation does not double-charge.

---

## 8. Known gaps (honest follow-ups)

1. **API-level dedup on generate** — finalized invoices still enqueue (202); worker skips side effects. Optional improvement: read status before enqueue.
2. **PEL reclaim** — pending stream messages after worker crash should be reclaimed (e.g. XAUTOCLAIM) in production.
3. **DB pool sizing** — documented rule for assignment; production likely needs larger pool or separate handler/worker pools.
4. **Pricing** — sum of usage only; real billing needs a pricing engine on aggregates.

---

## 9. Summary for reviewer

| Question | Answer |
|----------|--------|
| **What was given?** | Log-based failure scenario + API contracts + multi-tenant context. |
| **What was the problem?** | Shared resources + long-held Rating work → pool collapse → Redis cascade → Billing broken. |
| **What did we solve?** | Workload separation, queues, concurrency caps, aggregates, async generate, split Redis, fair workers, shedding, idempotency. |
| **What are the tradeoffs?** | Seconds of ingest lag before calculate; 429 under load; sync Rating vs async Billing split; assignment scale vs production Kafka/multi-pool evolution. |

This document describes **intent and decisions**. Implementation details, API reference, and run instructions live in the repository README and runbook.
