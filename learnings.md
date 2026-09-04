# ALETHEIA: Complete Technical Learning & Engineering Guide

This document breaks down **ALETHEIA** from first principles. It is written to give you a deep, confident technical understanding of the architecture, design choices, trade-offs, and security boundaries so you can explain it fluently in **AI Engineering, DevOps, and Backend Engineering** interviews.

---

## 1. Executive Summary & Problem Statement

### What problem does ALETHEIA solve?
In modern cloud environments (Kubernetes, AWS, Datadog, Prometheus), software systems crash or throw exceptions continuously. On-call engineers receive alerts via PagerDuty/Datadog and manually inspect logs, locate source code, write a patch, run local tests, and open a GitHub Pull Request (PR).

**ALETHEIA (Autonomous AIOps Platform)** automates the entire incident remediation pipeline:
1. **Ingest:** Accepts alert webhooks from monitoring systems.
2. **Analyze & Fix:** Uses Google Gemini AI to locate the root cause and generate a unified Git patch diff (`.patch`).
3. **Validate:** Executes an automated Git dry-run inside a temporary isolated environment.
4. **Human Safety Gate:** Displays the diff in an operational command center UI for human review.
5. **Remediate:** Opens a GitHub Pull Request upon human approval.

---

## 2. High-Level System Architecture

```text
┌─────────────────────────┐
│ Monitoring Systems      │ (Datadog / Prometheus / Custom Webhooks)
└───────────┬─────────────┘
            │ HTTP POST /api/v1/webhooks/ingest
            ▼
┌────────────────────────────────────────────────────────┐
│ FastAPI Backend Engine (Port 8001)                      │
│                                                        │
│ 1. Security Gate (HMAC SHA-256, Rate Limiting, Keys)  │
│ 2. Alert Normalizer (Generic -> Standard Schema)       │
│ 3. Gemini AI Patcher (Prompt + Target Code -> Diff)   │
│ 4. Git Applier (Isolated local worktree dry-run)       │
│ 5. Audit Event Logger (PostgreSQL / AuditLog)         │
└───────────┬────────────────────────────────────────────┘
            │
            ├───────────────────────┐
            ▼                       ▼
┌────────────────────────┐  ┌────────────────────────┐
│ PostgreSQL + pgvector  │  │ React Operational UI   │ (Port 5174)
│ DB (Port 5435)         │  │ Command Center Dashboard│
└────────────────────────┘  └────────────────────────┘
```

---

## 3. Core Technical Deep Dives (Interview Knowledge)

### A. Webhook Security & Ingestion Layer
* **HMAC SHA-256 Signature Verification:** Webhooks sent over the public internet can be spoofed. We use `X-Hub-Signature-256` HMAC validation so the backend only processes payloads signed with our secret key (`WEBHOOK_SECRET`).
* **Idempotency Control:** Network retries can resend the same webhook. We track `X-Idempotency-Key` or payload digests to guarantee a single incident is processed once (idempotent execution).
* **Sliding-Window Rate Limiting:** Built-in rate-limiting prevents Denial of Service (DoS) attacks on the `/ingest` route.

### B. AI Patch Generation (Structured LLM Output)
* **Prompt Construction:** We feed the LLM two things:
  1. The raw exception traceback / log.
  2. The target file's existing source code read from the local repository.
* **Structured Output Schema:** Rather than raw markdown, we enforce Pydantic structured output (`PatchResult`) from Gemini containing:
  - `bug_description` (Root cause summary)
  - `explanation` (Technical reasoning)
  - `unified_diff` (Standard unified Git diff format)
  - `confidence_score` (Float between 0.0 and 1.0)

### C. Git Worktree Isolation & Dry-Run Testing
* **Why not test directly in the working directory?** Modifying the main checked-out branch can corrupt live server code or cause race conditions when multiple incidents run concurrently.
* **Git Worktrees (`git worktree`):** ALETHEIA creates a temporary, detached Git worktree directory on disk, applies the unified diff (`git apply`), verifies syntactic correctness, and deletes the worktree. The main checkout remains untouched!

### D. Human-in-the-Loop Safety Approval Gate
* **Server-Side Enforcement:** Automated AI code pushes to production branches carry risk. ALETHEIA halts pipeline progress at `DRY_RUN_PASSED`.
* The `POST /api/v1/jobs/{job_id}/approve` endpoint enforces server-side authorization before invoking GitHub API calls to push the branch and open a PR.

### E. Database Layer & Audit Logging
* **SQLAlchemy (AsyncIO) + PostgreSQL:** The backend uses `asyncpg` with PostgreSQL for non-blocking database queries.
* **Audit Logs (`audit_logs` table):** Records an append-only timeline of every event (`WEBHOOK_INGEST`, `PATCH_GENERATED`, `DRY_RUN_PASSED`, `APPROVAL_GRANTED`, `PR_CREATED`) for security compliance and auditability.

### F. Frontend Architecture (Orchid Noir System)
* Built using **React, TypeScript, and Vite**.
* Designed specifically as an **operational command center** (table-first layout, dense information hierarchy, restrained dark color tokens, monospace diff viewers, zero decorative marketing slop).
* Communicates with FastAPI via non-blocking polling and explicit API state indicators (`Connecting` | `Production` | `Demo data`).

---

## 4. Key Engineering Terminology to Use in Interviews

1. **AIOps (Artificial Intelligence for IT Operations):** Using machine learning and LLMs to automate incident triage and code fixes.
2. **Unified Diff Patch:** Standard Git diff format (`--- a/file.py`, `+++ b/file.py`, `@@ -1,3 +1,5 @@`) used by `git apply`.
3. **Idempotency:** A property where an operation can be applied multiple times without changing the result beyond the initial application.
4. **Git Worktree:** A feature of Git that allows multiple working trees attached to the same repository simultaneously.
5. **HMAC Signature:** Keyed-hash message authentication code used to verify payload authenticity and integrity.
6. **Graceful Degradation / Standalone Mode:** If PostgreSQL is unreachable, ALETHEIA falls back gracefully without crashing the web process.

---

## 5. Summary Table of Technology Stack

| Component | Technology Used | Why It Was Chosen |
| --- | --- | --- |
| **Backend Framework** | FastAPI (Python 3.13) | Asynchronous, ultra-fast, native OpenAPI docs & Pydantic validation |
| **Database** | PostgreSQL 16 + pgvector | Industrial-grade relational store with vector capabilities for semantic log search |
| **ORM** | SQLAlchemy 2.0 (Async) | Non-blocking database operations over `asyncpg` driver |
| **AI Model** | Google Gemini 3.6 / 1.5 Flash | High-speed structured JSON generation for patch diffs |
| **Frontend UI** | React 18 + TypeScript + Vite | Type-safe, instant HMR build, modular component design |
| **Icons & Style** | Lucide Icons + Orchid Noir CSS | Dark, professional, operational incident command system design |
