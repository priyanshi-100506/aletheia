# ALETHEIA: Complete Technical Learning & Engineering Guide

This document breaks down **ALETHEIA** from first principles. It is written to give you a deep, confident technical understanding of the architecture, design choices, trade-offs, and security boundaries so you can explain it fluently in **AI Engineering, DevOps, and Backend Engineering** interviews.

---

## 1. Executive Summary & Problem Statement

### What problem does ALETHEIA solve?
In modern cloud environments (Kubernetes, AWS, Datadog, Prometheus), software systems crash or throw exceptions continuously. On-call engineers receive alerts via PagerDuty/Datadog and manually inspect logs, locate source code, write a patch, run local tests, and open a GitHub Pull Request (PR).

**ALETHEIA (Autonomous AIOps Platform)** automates the entire incident remediation pipeline:
1. **Ingest & Validate:** Accepts alert webhooks with HMAC-SHA256 verification and Redis rate-limiting.
2. **Asynchronous Queue:** Offloads processing to an ARQ background worker over Redis, ensuring deterministic job IDs and instantaneous HTTP 202 responses.
3. **Analyze & Fix:** Uses Google Gemini 2.0 Flash AI with source code context inside strict path boundaries to generate a unified Git patch diff (`.patch`).
4. **Validate:** Executes an automated Git dry-run (`git apply --check`) inside an isolated temporary Git worktree.
5. **Human Safety Gate:** Displays the diff in an operational command center UI for human review.
6. **Remediate:** Performs TOCTOU dry-run re-verification, commits inside a fresh worktree, pushes to GitHub, and opens a Pull Request upon human approval.

---

## 2. High-Level System Architecture

```text
┌─────────────────────────┐
│ Monitoring Systems      │ (Datadog / Prometheus / Custom Webhooks)
└───────────┬─────────────┘
            │ HTTP POST /api/v1/webhooks/ingest (HMAC, Rate-Limit, Idempotency)
            ▼
┌────────────────────────────────────────────────────────┐
│ FastAPI API Gateway (Port 8001)                        │
│ 1. Verify HMAC SHA-256 signature                       │
│ 2. Redis sliding-window rate limit (30 req/min/IP)     │
│ 3. Pre-create job row in PostgreSQL                    │
│ 4. Enqueue job_id to Redis (ARQ queue) → Return 202    │
└───────────┬────────────────────────────────────────────┘
            │
            │ Async Job Pop (arq:queue)
            ▼
┌────────────────────────────────────────────────────────┐
│ ARQ Background Worker Process                          │
│                                                        │
│ 1. Safe Source Read: Path traversal & .env blocking   │
│ 2. Gemini 2.0 Flash: Structured JSON PatchResult       │
│ 3. Dry-Run Validation: git apply --check in worktree   │
│ 4. Set status: WAIT_FOR_APPROVAL                       │
└───────────┬────────────────────────────────────────────┘
            │
            │ On-Call Engineer Reviews Diff in React UI
            │ POST /api/v1/jobs/{job_id}/approve
            ▼
┌────────────────────────────────────────────────────────┐
│ GitHub PR Creation & Audit Trail                       │
│ 1. TOCTOU Re-check: git apply --check against HEAD     │
│ 2. Isolated Git Worktree: branch, apply, commit, push  │
│ 3. Token Sanitization: PAT scrubbed from logs/errors   │
│ 4. GitHub API: Open Pull Request                       │
│ 5. AuditLog: Append-only timeline in PostgreSQL        │
└────────────────────────────────────────────────────────┘
```

---

## 3. Core Technical Deep Dives (Interview Knowledge)

### A. Webhook Security & Ingestion Layer
* **HMAC SHA-256 Signature Verification:** Webhooks sent over the public internet can be spoofed. We use `X-Hub-Signature-256` HMAC validation so the backend only processes payloads signed with our secret key (`WEBHOOK_SECRET`).
* **Idempotency Control:** Network retries can resend the same webhook. We track `X-Idempotency-Key` using Redis `SET NX EX` to guarantee an incident is processed only once (idempotent execution).
* **Sliding-Window Rate Limiting:** Redis sorted set sliding-window rate limiting prevents Denial of Service (DoS) attacks on the `/ingest` route and persists across restarts and multi-instance replicas.

### B. Asynchronous Queue Architecture (ARQ + Redis)
* **Why ARQ?** ALETHEIA is 100% async Python (`asyncio`). Celery requires synchronous worker bodies or blocking adapters. ARQ is natively async, lightweight, and uses Redis for high throughput.
* **Deterministic Job IDs:** We pass the database `job_id` directly as the ARQ job identifier, ensuring that re-enqueuing the same incident cannot spawn duplicate worker tasks.
* **In-Process Worker Option:** For $0 free-tier cloud deployment (Render free tier), ALETHEIA can run the ARQ worker inside the FastAPI lifespan using `RUN_WORKER_INPROCESS=true`, conserving free instance hours.

### C. AI Patch Generation & Security Boundaries
* **Path Traversal Protection (`_safe_read_target_file`):** Resolves target file paths and checks `Path.is_relative_to(repo_root)`. Traversal attempts (e.g. `../../etc/passwd`) and sensitive files (`.env`, `id_rsa`, `*.pem`, `*.key`) are blocked from being ingested into prompts.
* **Prompt Delimitation:** Raw error logs and source files are wrapped in explicit XML tags (`<error_log>`, `<target_file>`) to prevent prompt injection and delimiter confusion.
* **Structured Output Schema:** Rather than raw markdown, we enforce Pydantic structured output (`PatchResult`) from Gemini containing `bug_description`, `explanation`, `unified_diff`, and `confidence_score`.

### D. Git Worktree Isolation & Dry-Run Testing
* **Why not test directly in the working directory?** Modifying the main checked-out branch can corrupt live server code or cause race conditions when multiple incidents run concurrently.
* **Git Worktrees (`git worktree`):** ALETHEIA creates a temporary, detached Git worktree directory on disk, applies the unified diff (`git apply`), verifies syntactic correctness, and deletes the worktree in a `finally` block. The main checkout remains untouched.

### E. Human-in-the-Loop Safety Approval Gate & TOCTOU Protection
* **Server-Side Enforcement:** Automated AI code pushes to production branches carry risk. Direct mutation via `/api/v1/patch/apply` is locked down (`dry_run=False` returns `403 Forbidden`).
* **TOCTOU Prevention:** When an engineer approves a patch via `POST /api/v1/jobs/{job_id}/approve`, the backend re-runs `git apply --check` against current `HEAD` before pushing to guarantee the branch hasn't diverged during the review period.
* **Credential Scrubbing:** All git subprocess error streams pass through `_sanitize_output()`, stripping Personal Access Tokens and remote authentication headers from logs and HTTP error responses.

### F. Frontend Architecture (Orchid Noir System)
* Built using **React 18, TypeScript, and Vite**.
* Designed specifically as an **operational command center** (table-first layout, dense information hierarchy, restrained dark color tokens, monospace diff viewers, zero decorative marketing slop).
* Communicates with FastAPI via non-blocking polling and explicit API state indicators (`Connecting` | `Production` | `Demo data`).

---

## 4. Key Engineering Terminology to Use in Interviews

1. **AIOps (Artificial Intelligence for IT Operations):** Using machine learning and LLMs to automate incident triage and code fixes.
2. **Unified Diff Patch:** Standard Git diff format (`--- a/file.py`, `+++ b/file.py`, `@@ -1,3 +1,5 @@`) used by `git apply`.
3. **Idempotency:** A property where an operation can be applied multiple times without changing the result beyond the initial application.
4. **Git Worktree:** A feature of Git that allows multiple working trees attached to the same repository simultaneously.
5. **HMAC Signature:** Keyed-hash message authentication code used to verify payload authenticity and integrity.
6. **TOCTOU (Time-of-Check to Time-of-Use):** A race condition where state changes between validation and execution; solved via pre-apply re-verification.

---

## 5. Technology Stack Summary

| Component | Technology Used | Why It Was Chosen |
| --- | --- | --- |
| **Backend Framework** | FastAPI (Python 3.13) | Asynchronous, ultra-fast, native OpenAPI docs & Pydantic validation |
| **Task Queue** | ARQ + Redis | Native `asyncio` task processing, low latency, lightweight |
| **Database** | PostgreSQL 16 (Neon compatible) | Industrial-grade relational store with asyncpg async driver |
| **AI Model** | Google Gemini 2.0 Flash | High-speed structured JSON generation for patch diffs |
| **Frontend UI** | React 18 + TypeScript + Vite | Type-safe, instant HMR build, modular component design |
| **Design System** | Orchid Noir + TailwindCSS | Dark, professional, operational incident command system design |
| **Cloud Hosting** | Render + Neon + Upstash + Vercel | 100% Free-Tier ($0/mo) production-ready deployment architecture |
