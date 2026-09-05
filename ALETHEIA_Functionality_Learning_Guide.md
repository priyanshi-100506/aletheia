# ALETHEIA Functionality Learning Guide

## Purpose

Learn what ALETHEIA itself does, how one incident moves through the system, where state changes, and where the implementation stops.

> ALETHEIA accepts normalized alerts, stores remediation jobs, asks Gemini for a structured candidate diff when configured, enforces a target-file policy, applies the patch in an isolated checkout, runs targeted validation, pauses for human approval, and attempts to create a GitHub pull request. The deterministic portfolio runner proves this path without Gemini or GitHub calls.

---

## Module 1 — What Is ALETHEIA?

### Problem

An on-call engineer receives a production error and must investigate the likely code location, write a fix, test it, review it, and open a pull request. ALETHEIA automates part of the repetitive alert-to-code workflow.

### User

On-call engineers and maintainers of small-to-medium services are the clearest intended users.

### Input and output

**Input:** generic, Prometheus-like, or Datadog-like alert JSON.

**Output:** a persisted remediation job, candidate AI diff, Git applicability result, human approval state, and a GitHub PR attempt.

### 30-second explanation

ALETHEIA receives an alert, asks Gemini for a code patch, checks whether Git can apply it, lets an engineer review it, and can create a GitHub PR. It is an approval-first remediation prototype, not autonomous production repair.

### 2-minute explanation

The FastAPI endpoint authenticates and normalizes an alert, stores a `RemediationJob` in PostgreSQL, and enqueues an ARQ task through Redis. The worker calls Gemini, persists a structured patch, runs `git apply --check`, and waits for approval. Approval triggers a recheck and a separate Git worktree where a branch is created, the patch is committed, pushed, and submitted to GitHub.

### 10-minute explanation

Use the complete incident lifecycle in Module 3. Always distinguish generated, applicable, tested, approved, PR-created, merged, deployed, and fixed. ALETHEIA currently implements only some of those states.

---

## Module 2 — System Components

| Component | Why it exists | What it owns | What it does not own |
|---|---|---|---|
| Frontend | Human dashboard and review | Display and approval requests | Truth, authorization, semantic correctness |
| FastAPI | HTTP boundary | Validation, request orchestration | Long-running work |
| PostgreSQL | Durable state | Jobs and audit rows | Queue delivery or GitHub state |
| Redis | Fast coordination | Rate limits, idempotency, ARQ transport | Complete durable workflow history |
| ARQ worker | Background execution | Pipeline processing | Human identity and authorization |
| Gemini | Candidate diagnosis and patch | Probabilistic output | Proof of correctness |
| Git | Patch and branch mechanics | Apply, commit, worktree, push | Whether the fix is conceptually right |
| GitHub | Remote collaboration | Branches, commits, PRs | Internal job state |
| Alert source | Incident signal | Error payload and context | Remediation decisions |

---

## Module 3 — Complete Incident Lifecycle

```text
Monitoring alert
  → POST /api/v1/webhooks/ingest
  → API-key check
  → Redis rate limit
  → HMAC check
  → optional idempotency
  → normalize_alert()
  → RemediationJob(PENDING)
  → ARQ enqueue
  → process_remediation_job()
        → Gemini or fixture PatchResult
        → GENERATED
        → isolated target-policy check and patch apply
        → PATCH_APPLIED
        → targeted tests/checks
        → VALIDATION_PASSED or VALIDATION_FAILED
  → WAIT_FOR_APPROVAL
  → approve endpoint
  → recheck patch
  → temporary worktree
  → branch, apply, commit, push
  → GitHub pull request
  → PR_CREATED
```

### 1. Alert ingress

`ingest_alert()` in `app/api/v1/endpoints/webhooks.py` reads the request, rate-limits it, verifies HMAC if configured, claims an optional idempotency key, normalizes the payload, inserts a job, commits, and enqueues.

**Failure:** database commit can succeed while enqueue fails, leaving a PENDING job that may never execute.

### 2. Normalization

`normalize_alert()` in `app/schemas/webhook.py` detects payload style. Prometheus-like payloads select firing alerts and may extract `labels.target_file`. Datadog-like payloads prefer message/body/error log/title.

### 3. Worker processing

`process_remediation_job()` records pipeline activity, changes state to GENERATING, calls `generate_patch()`, records PATCH_GENERATED, applies and validates the patch in an isolated checkout, records `PATCH_APPLIED` and `VALIDATION_PASSED` or `VALIDATION_FAILED`, then waits for approval unless auto-approve is explicitly enabled.

### 4. AI remediation

`generate_patch()` reads a safe target file, creates a prompt containing the error log and file content, calls Gemini through a thread, parses `PatchResult`, and persists the result.

The model does not receive repository-wide context, tests, dependency graph, history, deployment configuration, or runtime telemetry.

### 5. Patch validation

`validate_in_isolated_workspace()` copies the configured repository to a temporary checkout, rejects paths outside the requested target, applies the patch, and runs a supplied test command or Python syntax check. A clean Git apply is only one part of validation; a passing relevant test command is the evidence used for `VALIDATION_PASSED`.

### 6. Human review

`frontend/src/App.tsx` polls jobs every 15 seconds. `frontend/src/components/DiffViewer.tsx` displays the diff. Split mode is not actually split; it renders the same unified lines. Test and policy results are not shown.

### 7. Approval and PR

`approve_job()` calls `approve_and_create_pr()`. It rechecks the patch, records approval, creates a temporary worktree, creates a branch, applies and commits the patch, pushes it, and calls the GitHub pull request API.

---

## Module 4 — State Machine

```text
PENDING → GENERATING → GENERATED → PATCH_APPLIED → VALIDATION_PASSED → WAIT_FOR_APPROVAL → APPROVING → PR_CREATED
   ↘          ↘             ↘              ↘                  ↘
                         FAILED
```

| State | Meaning | Reality |
|---|---|---|
| `PENDING` | Stored but not processed | Can remain forever after queue failure. |
| `GENERATING` | AI work started | No explicit attempt history. |
| `GENERATED` | Patch result persisted | Structure, not correctness. |
| `PATCH_APPLIED` | Patch applied in isolated workspace | Does not alone prove correctness. |
| `VALIDATION_PASSED` | Targeted tests or checks passed | Evidence records the command and output. |
| `VALIDATION_FAILED` | Validation command failed | Blocks approval and PR creation. |
| `WAIT_FOR_APPROVAL` | Human review required | Normal default path. |
| `PR_CREATED` | PR flow reported success | `pr_simulated` distinguishes demo mode from a real GitHub PR. |
| `APPLIED` | Intended post-merge state | Merge/deployment transition is not implemented. |
| `FAILED` | Error or rejection | Rejection and technical failure are conflated. |

**Missing states:** RETRYING, CANCELLED, EXPIRED, CREATING_PR, PR_PUSHED, PR_UNKNOWN, MERGED, DEPLOYED, ROLLED_BACK, REJECTED.

---

## Module 5 — AI Remediation

### What the model receives

- Raw error log.
- Optional target file content.
- Target-file hint.

### What it produces

`PatchResult`: file path, explanation, bug description, unified diff, and confidence score.

### What is validated

- Response structure through Pydantic.
- Requested target-path allowlisting.
- Patch size, traversal, and absolute-path checks.
- Git applicability in an isolated checkout.
- Targeted tests or syntax checks when configured.

### What is not validated

- Root-cause truth.
- Diff minimality.
- Target-file consistency.
- Tests, lint, types, security scans.
- Whether the patch fixes the alert.
- Confidence calibration.

> **Core lesson:** A patch can apply cleanly while weakening authentication, changing CI, breaking a business rule, or failing to address the incident. Applicability is a textual property, not a correctness proof.

---

## Module 6 — Patch Safety

| Lifecycle stage | Status |
|---|---|
| Identify target file | Implemented, but model output is not fully constrained. |
| Generate unified diff | Implemented. |
| Reject traversal/sensitive reads | Partially implemented. |
| Check Git applicability | Implemented. |
| Isolated validation checkout | Implemented. |
| Run targeted tests | Implemented when a validation command is supplied. |
| Static/security analysis | NOT IMPLEMENTED. |
| Human approval | Implemented with an atomic approval claim. |
| Rollback | NOT IMPLEMENTED. |

---

## Module 7 — Human Approval

Approval exists because the model is probabilistic and the change can affect production code. The frontend displays status and diff, but not test results, policy results, verified affected files, base commit, or GitHub checks.

### Two approvals at once

```text
A reads WAIT_FOR_APPROVAL
A claims APPROVING
B loses the atomic claim
A performs the side effect
B receives the existing result or a conflict

Approval uses an atomic transition to `APPROVING`; a second request returns the existing PR identity or is rejected before side effects.

---

## Module 8 — Failure Scenarios

| Scenario | Current behavior | Desired behavior |
|---|---|---|
| PostgreSQL dies | Persistence fails. | Clear readiness failure and retryable state. |
| Redis dies | Rate limiting, idempotency, or queueing fails. | Controlled dependency failure and durable dispatch. |
| Gemini dies | Selected transient errors retry; orchestrator may end in FAILED. | Classified attempts, cost limits, and recovery. |
| Malformed JSON | Patch parsing fails. | Record model failure; bounded retry or human fallback. |
| Wrong code | Git may still accept it. | Tests, static checks, policy gates, and review evidence. |
| Patch conflict | Job fails. | Rebase/regenerate workflow. |
| Tests fail | Tests are not run. | Block approval and show failures. |
| GitHub fails | Job may fail after partial remote effects. | Find existing branch/PR and reconcile. |
| Worker crashes | ARQ may retry. | Idempotent side effects and attempt records. |
| Duplicate webhook | Only caller-key duplicates are prevented. | Server-derived incident fingerprints. |
| Malicious repository/log | Content reaches model or Git boundary. | Sandbox, allowlists, hostile-input policy, isolated execution. |

---

## Module 9 — Security Boundaries

```text
Alert provider / user
        ↓ untrusted HTTP, logs, actor
Frontend
        ↓ API requests
FastAPI
        ↓ authentication, validation
PostgreSQL + Redis
        ↓ durable state and queue
ARQ worker
        ↓ model context
Gemini
        ↓ generated diff
Git repository
        ↓ branch/push
GitHub
```

At every boundary ask: who controls the input, how is it authenticated, what validation occurs, what is persisted, what later trusts it, and what side effect it can cause?

---

## Module 10 — Business Workflow

```text
Traditional: alert → investigate → write fix → test → review → PR → deploy
ALETHEIA: alert → normalize → AI candidate → Git check → human review → PR attempt
```

Theoretical savings are alert-to-review time, repetitive investigation, boilerplate fix-writing, and alert-to-PR latency. No savings metric is currently measured.

---

## Module 11 — Current Limitations

| Category | Why it exists | Why it matters | Priority |
|---|---|---|---|
| Technical | Duplicate DB module; `create_all` schema setup. | Maintenance and safe evolution suffer. | P1 |
| Security | Shared key; optional HMAC; client actor. | Weak access control and audit trust. | P0 |
| Reliability | No outbox or reconciliation. | Stuck jobs and duplicate PRs. | P0 |
| AI | Small context; no semantic gates. | Wrong or dangerous patches. | P0 |
| Scalability | Shared checkout and model dependence. | Contention and cost grow quickly. | P1 |
| Product | Broad claims exceed proof. | User trust declines. | P0 |
| Operational | Logs without metrics/traces. | Failures are difficult to explain. | P1 |

---

## Module 12 — What ALETHEIA Is Not

Based on the code, ALETHEIA is currently:

- Not fully autonomous production remediation.
- Not a guarantee that incidents are fixed.
- Not proven semantic code correction.
- Not enterprise-ready.
- Not multi-tenant.
- Not fully authorized by user or repository.
- Not infinitely scalable.
- Not a complete AIOps platform.
- Not a RAG-powered code intelligence system.
- Not a test-backed patch validation system.
- Not a real-time activity platform.
- Not guaranteed to create a real PR when GitHub credentials are absent.
- Not proven against live PostgreSQL, Redis, Gemini, or GitHub.

---

# Recommended Study Sequence

## 1. HTTP and REST

**Why needed:** Everything begins with alert ingestion and approval requests.

**Learn:** HTTP methods, headers, JSON, status codes, request lifecycle, authentication.

**Read:** `app/api/v1/endpoints/webhooks.py`, `app/api/v1/endpoints/approval.py`, `app/api/v1/endpoints/jobs.py`.

**You should explain:** Why webhook ingestion returns `202` instead of waiting for Gemini.

## 2. Python Modules and Type Models

**Why needed:** You need to understand how the repository is divided.

**Learn:** Imports, packages, classes, enums, type hints, Pydantic.

**Read:** `app/config.py`, `app/schemas`, `app/models`.

**You should explain:** The difference between a Pydantic request schema and a SQLAlchemy database model.

## 3. FastAPI

**Why needed:** FastAPI is the backend entry point.

**Learn:** Routers, dependencies, lifespan, validation, response models.

**Read:** `app/main.py`, `app/api/v1/router.py`, `app/security.py`.

**You should explain:** How one request reaches `ingest_alert()`.

## 4. Async Python

**Why needed:** The API, database, Redis, and worker use asynchronous code.

**Learn:** Event loops, coroutines, `await`, blocking work, threads.

**Read:** `app/services/patcher.py`, `app/db/database.py`, `app/services/orchestrator.py`.

**You should explain:** Why Gemini is moved into a thread.

## 5. PostgreSQL and Transactions

**Why needed:** Jobs and audit history are persisted there.

**Learn:** Tables, rows, transactions, commit, rollback, constraints, connection pools.

**Read:** `app/db/database.py`, `app/models/remediation.py`, `app/models/audit.py`.

**You should explain:** Why database commit followed by queue enqueue can lose work.

## 6. SQLAlchemy

**Why needed:** The application uses SQLAlchemy’s async ORM.

**Learn:** Engine, session, ORM, queries, flush versus commit.

**Read:** `app/db/database.py`, `app/services/orchestrator.py`.

**You should explain:** What makes a database change durable.

## 7. Redis

**Why needed:** Redis supports rate limits, idempotency, and ARQ.

**Learn:** Keys, TTL, sorted sets, atomic commands, availability.

**Read:** `app/services/redis_store.py`.

**You should explain:** Why `SET NX EX` helps deduplication but does not make the whole workflow atomic.

## 8. Queues and ARQ

**Why needed:** Remediation is background work.

**Learn:** Queue, worker, retry, timeout, job result, at-least-once execution.

**Read:** `app/worker.py`, `app/services/queue_service.py`, `app/services/orchestrator.py`.

**You should explain:** Why a worker can execute a job more than once.

## 9. State Machines and Concurrency

**Why needed:** Approval and retries are stateful concurrent operations.

**Learn:** Race conditions, compare-and-set, locks, idempotency, state transition invariants.

**Read:** `app/models/remediation.py`, `app/api/v1/endpoints/approval.py`.

**You should explain:** Exactly how two simultaneous approvals can create duplicate side effects.

## 10. Git

**Why needed:** Git is the patch and branch execution engine.

**Learn:** Repositories, commits, branches, worktrees, diffs, patch application, conflicts.

**Read:** `app/services/git_applier.py`, `app/services/github_service.py`.

**You should explain:** What `git apply --check` proves and does not prove.

## 11. GitHub API

**Why needed:** The final product output is a pull request.

**Learn:** Tokens, branches, commits, PR APIs, partial failure, rate limits.

**Read:** `app/services/github_service.py`.

**You should explain:** What happens if pushing succeeds but PR creation fails.

## 12. Docker and Deployment

**Why needed:** The application consists of multiple services.

**Learn:** Images, containers, Compose, networking, environment injection, volumes.

**Read:** `docker-compose.yml`, `Dockerfile.backend`, `Dockerfile.worker`, `render.yaml`.

**You should explain:** How the frontend, backend, database, Redis, and worker communicate.

## 13. Security

**Why needed:** The system processes production logs and can modify source code.

**Learn:** Authentication, authorization, HMAC, replay attacks, path traversal, prompt injection, secret handling, subprocess boundaries.

**Read:** `app/security.py`, `app/services/security_service.py`, `app/services/git_applier.py`, `app/services/github_service.py`.

**You should explain:** Why a valid HMAC does not authorize a user to approve every repository job.

## 14. LLM Integration

**Why needed:** Gemini generates the proposed patch.

**Learn:** Prompt construction, structured output, retries, untrusted context, hallucination, evaluation.

**Read:** `app/services/patcher.py`, `app/schemas/patch.py`.

**You should explain:** Why model confidence is not evidence of correctness.

## 15. Testing and Observability

**Why needed:** You need evidence that the system works and can be debugged.

**Learn:** Unit tests, integration tests, E2E tests, mocks, metrics, traces, readiness, queue depth.

**Read:** `tests`, `app/main.py`.

**You should explain:** What the passing tests prove and what they do not prove.

---

# Knowledge Check

Do not read the answers until you have attempted each question.

## Level 1 — Fundamentals

1. What is a Python module versus package?
2. Why use environment variables?
3. What does Pydantic validate?
4. What is a coroutine?
5. Why can blocking code damage an async server?
6. Authentication versus authorization?
7. What does 202 mean?
8. What is a transaction?
9. What is Redis TTL?
10. What is a worktree?

## Level 2 — Functionality

11. Which endpoint receives alerts?
12. What happens before normalization?
13. What record represents an incident?
14. Which component performs background work?
15. What does Gemini produce?
16. What is the difference between `PATCH_APPLIED` and `VALIDATION_PASSED`?
17. Why wait for approval?
18. Which endpoint approves?
19. What happens during PR creation?
20. Which states are missing?

## Level 3 — Backend

21. Why separate routes and services?
22. Why run Gemini in a thread?
23. Why use a connection pool?
24. Why is `create_all` not migrations?
25. Why Redis if PostgreSQL exists?
26. What does ARQ do?
27. Why can retries duplicate effects?
28. What is idempotency?
29. Why is a local semaphore insufficient?
30. Why use a background queue?

## Level 4 — Failure

31. What if DB commit succeeds but enqueue fails?
32. What if the worker catches an exception?
33. What if Gemini returns malformed JSON?
34. What if the patch cannot apply?
35. What if tests fail?
36. What if push succeeds but PR creation fails?
37. What if two people approve?
38. What if the webhook repeats without a key?
39. What if Redis dies?
40. What if the repository changes after dry run?

## Level 5 — Security

41. Why is optional HMAC dangerous?
42. How can logs cause prompt injection?
43. Why is actor client-controlled weak?
44. Why is a token in a subprocess URL risky?
45. Why validate patch paths?
46. Does Git applicability prove safety?
47. What access does the shared key provide?
48. Why restrict simulated PRs to demo mode?

## Level 6 — Architecture

49. Why are DB commit and enqueue not atomic?
50. What does an outbox change?
51. Why use worktrees?
52. Why is dry-run not isolated?
53. Who owns remediation state?
54. Who owns remote PR state?
55. Why can DB and GitHub disagree?
56. Why use an explicit state machine?
57. What does reconciliation do?
58. Why is the frontend not the source of truth?

## Level 7 — Senior Reasoning

59. What is the smallest trustworthy product?
60. What evidence proves time savings?
61. Which changes should never auto-approve?
62. What if a PR exists but DB says failed?
63. Why start with narrow incident classes?
64. What invariant should approval enforce?
65. What invariant should PR creation enforce?
66. Which metrics reveal model usefulness?
67. Which tests reduce risk most?
68. What feature creates misleading confidence?
69. What should be fixed before adding more integrations?
70. What is the difference between a credible demo and a production system?

---

# Answer Key

1. A file versus a collection of modules.
2. Environment-specific values and secrets.
3. Runtime shape and declared rules.
4. Suspendable event-loop computation.
5. It blocks other coroutines.
6. Identity/access versus permitted actions.
7. Accepted for asynchronous processing.
8. Atomic group of database operations.
9. Retention duration.
10. A second directory attached to a repository.
11. `POST /api/v1/webhooks/ingest`.
12. Authentication, rate limit, HMAC, optional idempotency.
13. `RemediationJob`.
14. ARQ worker.
15. `PatchResult`.
16. Git can likely apply it.
17. Human review is the safety boundary.
18. `/jobs/{id}/approve`.
19. Worktree, branch, apply, commit, push, GitHub API.
20. Retrying, cancellation, merge, deploy, rollback, and applied transitions.
21. Separation of concerns.
22. The SDK call is blocking.
23. Reuse and limit database connections.
24. It does not version existing schemas.
25. Rate limits, idempotency, and queue transport.
26. Background job execution.
27. Side effects can repeat.
28. A repeat-safe operation key.
29. Other processes do not share it.
30. To keep long work out of the HTTP request.
31. A stuck `PENDING` job.
32. ARQ may not retry.
33. Parsing fails.
34. The job fails, with no regeneration path.
35. Tests are not run currently.
36. A remote branch may exist without a known PR.
37. Duplicate side effects.
38. Duplicate jobs.
39. Dependency operations fail.
40. Stale validation and TOCTOU risk.
41. It permits forged alerts.
42. Raw log content reaches the model.
43. The caller can claim any identity.
44. Process inspection or diagnostics may expose it.
45. To prevent repository escape.
46. No, it only proves textual applicability.
47. Global job and approval access.
48. To prevent fake success being mistaken for delivery.
49. The database and Redis use separate commit systems.
50. Durable dispatch intent and retry.
51. Isolation for branch operations.
52. Dry-run uses the configured repository directory.
53. PostgreSQL job state.
54. GitHub branches, commits, and pull requests.
55. Partial external side effects.
56. To make legal states explicit.
57. Compare and repair cross-system state.
58. Backend and external systems hold actual state.
59. An approval-first assistant for one repository and recurring errors.
60. Controlled incidents with accepted, passing patches and lower time-to-PR.
61. Security, infrastructure, dependencies, CI, secrets, migrations, and deployments.
62. Find and record the existing PR; reconcile instead of duplicating.
63. Narrow classes have predictable context and tests.
64. Only one caller wins approval-to-creation.
65. One remediation maps to one branch and PR.
66. Acceptance, test-pass, rollback, latency, cost, and scope metrics.
67. Approval races, real patch application, GitHub partial failures, and queue recovery.
68. Applicability check plus model confidence plus simulated PR.
69. Security defaults, semantic validation, idempotency, recovery, and proof.
70. A demo shows the happy path; production requires trustworthy behavior under failure, attack, concurrency, and change.

---

## Final Mental Model

> ALETHEIA is a distributed workflow, not just a FastAPI app. The difficult engineering lies at boundaries: PostgreSQL versus Redis, retries versus side effects, model output versus Git, approval versus authorization, and GitHub reality versus database state.

To defend the system honestly, say what each state proves, what it does not prove, and how the system behaves when the next dependency fails.
