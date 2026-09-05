# ALETHEIA Frontend Blueprint

This document defines the frontend experience for the backend that exists today. It is a design and product blueprint, not an implementation requirement.

## Product Goal

Give an on-call engineer a fast, trustworthy answer to three questions:

1. What incident was detected?
2. What does ALETHEIA believe is wrong, and what will it change?
3. Is the change safe, and what action should I take next?

The product should feel operational rather than promotional: dense information, strong hierarchy, restrained color, and clear approval boundaries.

## Primary Navigation

- **Incidents**: active and historical remediation jobs.
- **Review Queue**: generated patches waiting for human approval.
- **Repositories**: configured repository and branch health.
- **Activity**: audit trail of ingestion, analysis, validation, and PR events.
- **Settings**: API integrations, policies, users, and retention.

Global controls: repository selector, environment selector, search, notifications, and user menu.

## Core Screens

### Incident Command Center

The first screen is a work queue, not a landing page.

- Header with open incident count, failed jobs, and readiness state.
- Filter bar for status, severity, source, repository, target file, and time range.
- Dense table with severity icon, alert title, source, repository, current state, confidence, age, and next action.
- Right-side detail drawer preserves list context while inspecting an incident.
- Empty state explains that no incidents require action, without decorative marketing content.

### Incident Detail

Use a two-column desktop layout and stacked mobile layout.

Left column:

- Incident identity, source, timestamps, labels, and target file.
- Sanitized error log in a monospace viewer with line wrapping and copy action.
- Related alerts and previous attempts.

Right column:

- State timeline: Pending, Generating, Generated, Dry Run Passed, PR Created, Failed.
- Confidence score with textual interpretation, never color alone.
- Root-cause summary and explanation.
- Patch review panel with file tabs, unified diff, added/removed line counts, and affected-file count.
- Actions: approve and create PR, reject, retry, or open repository.

The primary action must remain disabled until isolated validation passes and the user has reviewed the diff. A clean patch application alone is not sufficient.

### Patch Review

Treat this as a safety-critical review surface.

- Split or unified diff mode toggle.
- Syntax highlighting and line numbers.
- Expandable context around changed hunks.
- Warning strip for broad changes, generated files, dependency files, or files outside the requested target.
- Test and policy results beside the diff.
- Sticky approval footer with explicit text such as `Approve and create pull request`.
- Never hide the exact branch name or PR base branch.

### Job Activity

An event timeline should show:

- Alert received.
- Payload normalized.
- Job persisted.
- Gemini generation started/completed.
- Patch applied in isolated workspace.
- Targeted validation started/passed/failed, including command and evidence.
- Worktree created and branch pushed.
- Pull request created.
- Failure reason and retry eligibility.

Use polling initially against `GET /api/v1/jobs/{job_id}`. Add server-sent events or WebSocket updates only when the backend has a durable event stream.

### Repository View

- Repository URL and default branch.
- Last successful checkout and push check.
- Active remediation branches.
- Open ALETHEIA pull requests.
- Policy configuration: allowed paths, maximum diff size, required checks, and approval count.

### Settings and Integrations

Use separate panels for:

- Gemini connection status.
- GitHub connection and repository selection.
- Webhook endpoint and signing configuration.
- Authentication/API keys.
- Retention and redaction policy.
- Concurrency and approval policy.

Secrets should be write-only fields with masked values and rotation timestamps. Never display token values after submission.

## Visual Direction: Orchid Noir

The visual identity uses Orchid Noir and Sunshine as brand colors, while keeping status colors functionally separate. The product is an operational incident tool, so color must communicate safety before decoration.

### Tokens

```css
:root {
	--orchid-900: #24081F;
	--orchid-800: #3A0940;
	--orchid-600: #6B1F63;
	--orchid-100: #EFE3EC;

	--sunshine-500: #FADE85;
	--butter-400: #FFF3C4;

	--canvas: #F7F4F1;
	--paper: #FFFFFF;
	--hairline: #DED4D9;
	--text-secondary: #5B4F58;
	--text-disabled: #A79CA3;

	--status-success: #0E6B5C;
	--status-caution: #A85D14;
	--status-danger: #7A1F2B;
	--status-info: #35507A;
}
```

Brand tokens are used for chrome, navigation, the wordmark, confidence meters, active tabs, and a small number of key numerals. Status tokens are never replaced with orchid or sunshine.

### Color Rules

- No gradients anywhere.
- Sunshine is a highlight only: meter fills, thin indicators, active underlines, and occasional key numerals. It is never a large background or text color.
- Use Orchid Noir for brand identity, not success or validation.
- Pair every status color with a text label and matching icon; never communicate status by color alone.
- Use one bold brand moment: the dark orchid navigation rail with a thin Sunshine active indicator.
- Use `orchid-900` text on Sunshine and Butter surfaces. Never use white text on either yellow.
- Use status colors with white text only where contrast is sufficient.

### Component Mapping

| Component | Treatment |
| --- | --- |
| Navigation rail | `orchid-900` background, light text, 2px `sunshine-500` active bar |
| Primary action | `orchid-800` fill, white text, `orchid-600` hover, disabled grey until safe |
| Secondary action | `paper` fill, `hairline` border, `orchid-900` text |
| Confidence meter | Hairline track, `sunshine-500` fill, `orchid-900` numeric label beside it |
| Status badge | Solid functional status color, white text, matching icon and label |
| Selected table row | `orchid-100` background, no shadow |
| Diff and log panes | `orchid-900` background with light monospace text |
| Diff markers | `status-success` for additions and `status-danger` for removals only |
| Links outside navigation | `status-info`, reserving orchid for brand chrome |

Do not wrap every content block in a rounded card. Use hairline rules and full-width layout bands for tables and sections. Reserve cards for repeated items, drawers, modals, and genuinely framed tools. Use near-square corners for code and log panes, and only slight rounding for buttons and chips.

### Typography

- **Display:** Fraunces variable serif for the ALETHEIA wordmark and page-level section titles only.
- **UI:** IBM Plex Sans for tables, controls, labels, metadata, and body copy.
- **Monospace:** IBM Plex Mono for logs, diffs, IDs, branches, and file paths.

Do not use tracked-out all-caps labels, italicized or recolored single words in headings, or eyebrow labels above headings. Keep type compact and readable inside operational surfaces.

### Anti-Slop Constraints

- No purple decorative washes, gradient backgrounds, bokeh, or oversized hero sections.
- No identical soft shadow and radius treatment across the interface.
- Do not append arrows to every button or link.
- Separate metadata with layout, hairlines, or stacked lines rather than repeated middle dots.
- Motion must explain an action, such as a drawer opening or status changing to validated. Do not animate every row on page load.

## Interaction Rules

- Every asynchronous operation has visible pending, success, failure, and retry states.
- Preserve filters and scroll position when opening or closing an incident.
- Optimistically show the queued state after webhook submission, then reconcile with the job endpoint.
- Use progressive disclosure for raw payloads and verbose logs.
- Confirm destructive actions such as reject, cancel, or branch deletion.
- Show an explicit stale-data timestamp on detail views.
- Keyboard support: `/` focuses search, `j/k` moves through incidents, `Enter` opens, and `Escape` closes drawers.
- Tooltips name unfamiliar icon-only actions. Text labels remain for high-risk actions.

## Responsive Layout

Desktop uses a persistent navigation rail, dense incident table, and detail drawer. Tablet collapses the rail and keeps the table as the primary surface. Mobile uses a bottom navigation bar, stacked incident summaries, and a full-screen detail route rather than a drawer.

Diffs and logs must scroll horizontally within their own viewport. Long paths and branch names wrap or truncate with a copy action; they must never resize surrounding controls.

## Backend Contracts

Current frontend-facing endpoints:

- `GET /health`: process liveness.
- `GET /ready`: PostgreSQL readiness.
- `POST /api/v1/webhooks/ingest`: returns `{ status, job_id }` with HTTP `202`.
- `POST /api/v1/patch/generate`: returns a generated patch and job ID.
- `POST /api/v1/patch/apply`: validates or applies a diff.
- `GET /api/v1/jobs/{job_id}`: returns status, target file, timestamps, and failure message.

The frontend must not embed `X-API-Key` or any other long-lived secret in its build. Do not place credentials in URLs or browser local storage; use secure, HttpOnly session cookies through a same-origin frontend or backend-for-frontend proxy for protected routes.

## Loading and Latency Strategy

Zero latency is not physically possible for LLM, Git, database, or GitHub operations. The frontend should provide perceived immediacy:

- Return the user to the incident queue immediately after submission.
- Render the job shell and timeline before details arrive.
- Poll with backoff while the job is active and stop after terminal state.
- Cache repository metadata and completed job details.
- Stream log/timeline events when the backend later supports it.
- Never fake completion; distinguish queued, running, validated, and PR-created states.

## Accessibility and Trust

- Meet WCAG 2.2 AA contrast targets.
- Support full keyboard navigation and visible focus.
- Announce state changes through an accessible live region.
- Pair every color status with a label and icon.
- Keep exact timestamps, branch names, file paths, and PR URLs visible and copyable.
- Make approval intent explicit and record the reviewing user in the activity timeline.

## Suggested Build Order

1. App shell, navigation, incident table, and status badges.
2. Incident detail route with timeline and job polling.
3. Diff viewer and approval workflow.
4. Repository and integration settings.
5. Activity audit view and notification center.
6. Responsive and accessibility pass.
7. Streaming updates after the backend adds durable events.
