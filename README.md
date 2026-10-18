# Nod

**Give good work the green light.**

Nod takes a document from submission to a clear decision. Submitters choose a reviewer, reviewers approve or reject with feedback, and both can follow the same status and history.

**[Live app](https://nod.haggle.site)** · **[Swagger API](https://nod.haggle.site/api/docs/)** · **[Video walkthrough](https://www.loom.com/share/de45ca5f5bcd46ac9bc88a4df1e73db1)**

[![Play the Nod walkthrough on Loom](https://cdn.loom.com/sessions/thumbnails/de45ca5f5bcd46ac9bc88a4df1e73db1-0d5744cf2279f98e.gif)](https://www.loom.com/share/de45ca5f5bcd46ac9bc88a4df1e73db1)

## Try the workflow

1. Register and verify your email. On the live app, check Spam if the OTP is missing.
2. Upload a PDF, DOCX, or TXT file (up to 10 MB), or write plain text. Choose another verified user as reviewer.
3. The reviewer opens **Assigned to me**, previews the document, and approves or rejects it. Rejection requires feedback.
4. The submitter sees the decision and timeline in **My submissions**. Search and status filters help track work.

Verified users can both submit and review. Only the submitter and assigned reviewer can access a submission; only the assigned reviewer can decide. This version supports one team and one reviewer per submission. Submitted content and final decisions cannot be edited.

## Run locally

### Docker: frontend and backend together

With Docker and Docker Compose installed:

```bash
docker compose up --build
```

Open **http://localhost:8080**. This starts the frontend, API, PostgreSQL, and upload worker, applies migrations, and seeds demo data. No Azure credentials are needed locally; DOCX preview support is included in the image.

Use `jamie@nod.demo`, `alex@nod.demo`, or `sam@nod.demo`, all with password **`NodDemo!2026`**. Submit as Jamie, review as Alex, then switch back to see the outcome. These accounts are local-only; register on the live app.

For local registration, OTPs appear in the API logs:

```bash
docker compose logs -f api
```

### Separate frontend and backend development

Requires Python 3.12+ and Node 24+. From the repository root:

```bash
make setup          # Installs BE/FE dependencies, creates .env, and migrates the DB
make seed           # Creates local demo accounts and submissions
make api            # Terminal 1: Django at http://127.0.0.1:8000
```

In two additional terminals, from the same directory:

```bash
make worker         # Terminal 2: upload validation
make web            # Terminal 3: React at http://127.0.0.1:5173
```

The frontend proxies `/api` to Django. The supplied `.env.example` uses SQLite, local files, and console OTPs; `make setup` preserves an existing `.env`. Native DOCX previews require LibreOffice (`NOD_LIBREOFFICE_BINARY` can point to `soffice`); Docker already includes it. Keep `.env` and credentials out of Git.

## How it is built

- **Frontend:** React, TypeScript, and Vite, with submission and review views, document previews, and loading/error states.
- **Backend:** Django REST Framework with separate authentication, submission, and upload modules. PostgreSQL stores users, documents' metadata, decisions, and history.
- **Private files:** Production uploads go directly to Azure Blob Storage using short-lived signed URLs. A worker validates files before attachment; preview/download links require access checks. DOCX previews use LibreOffice.
- **Authentication and correctness:** Azure email OTP, HttpOnly session cookies, CSRF protection, and rate limits. Transactions, row locks, and idempotent requests protect against duplicate submissions and conflicting decisions.
- **Deployment:** Docker and Nginx on an Azure VM over HTTPS. Blob Storage and Azure Communication Services use managed identity; credentials stay outside source control.

## API design

### Interactive Swagger

Open **[Swagger UI](https://nod.haggle.site/api/docs/)** or download the **[OpenAPI JSON](https://nod.haggle.site/api/schema/)**. Locally use `/api/docs/` on port **8080** (Docker), **5173** (frontend), or **8000** (API).

1. Expand `auth/login/`, click **Try it out**, enter your credentials, and **Execute**. Local demo credentials are prefilled; use a registered account on production. You can also call `auth/register/` and `auth/verify/` with your email code.
2. Execute `reviewers/list/` and copy another user's `id`.
3. Execute `submissions/create/` with that `reviewer_id`, a fresh UUID `client_request_id`, and either text `content` or a validated `upload_id`. The response includes the submission `id`.
4. Execute `auth/logout/`, log in as the assigned reviewer, then execute `submissions/decision/{id}/` with `approved` or `rejected` (feedback required).
5. Use detail/history endpoints to inspect the result. These are real API calls and create real data on the selected server.

Swagger automatically sends session cookies and the current CSRF token, including after login; no manual **Authorize** step is needed. Request examples, response schemas, filters, validation errors, and retry behavior are included. The file workflow is **create upload → PUT bytes to the signed URL → complete → poll ready → submit**.


The JSON API uses `/api/v1/`; file transfer and preview URLs return or accept file bytes. Public IDs are UUIDs. First call `GET auth/bootstrap/`, retain cookies, and send its `csrf_token` as `X-CSRFToken` on POST requests, including login and registration. Successful login/verification returns a replacement token and sets the session cookie.

The table describes request bodies and the response's `data` field; `?` marks optional fields.

| Method / endpoint | Request → response |
|---|---|
| `GET auth/bootstrap/` | → `{csrf_token, demo_enabled}` |
| `POST auth/register/` | `{name, email, password}` → `{challenge_id, expires_in, resend_after}` |
| `POST auth/verify/` | `{challenge_id, code}` → `{user, csrf_token}` |
| `POST auth/resend/` | `{challenge_id}` → `{challenge_id, expires_in, resend_after}` |
| `POST auth/login/` | `{email, password}` → `{user, csrf_token}` |
| `POST auth/logout/` | → success message; invalidates the session |
| `GET auth/me/` | → current user |
| `GET reviewers/list/` | → eligible users, excluding yourself |
| `POST uploads/create/` | `{filename, size, content_type?}` → `{upload_id, upload_url, method, headers, expires_in, local}` |
| `POST uploads/complete/{id}/` | → upload state; queues validation after transfer |
| `GET uploads/status/{id}/` | → `{upload_id, status, error, name}` |
| `POST submissions/create/` | `{title, reviewer_id, client_request_id, content}` or replace `content` with `upload_id` → submission detail |
| `GET submissions/list/` | Query: `scope=mine` or `assigned`, `status`, `search`, `page` → `{results, count, page, pages}` |
| `GET submissions/detail/{id}/` | → submission detail |
| `POST submissions/decision/{id}/` | `{decision: "approved" or "rejected", note?}` → updated submission; rejection requires `note` |
| `GET submissions/history/{id}/` | → events with actor, previous/new status, note, and timestamp |
| `GET submissions/summary/` | Query: `scope` → status counts, total, and oldest pending timestamp |
| `GET submissions/file-link/{id}/` | → `{url, expires_in, content_type}`; `?download=true` requests the original file |

A user has `{id, name, email, can_review}`. Upload bytes go to the returned URL using its method and headers; then call `complete` and poll until `ready`. Cloud transfers do not include Nod cookies or CSRF headers. Local development instead uses the session-protected `PUT uploads/content/{id}/?token=…`; local preview links use `GET submissions/content/{id}/?token=…`. `/api/health/` and `/api/ready/` provide process and database checks.

### Request and response examples

Create a text submission with `POST /api/v1/submissions/create/`:

```json
{
  "title": "Launch plan",
  "content": "Please review the proposed launch checklist.",
  "reviewer_id": "22222222-2222-4222-8222-222222222222",
  "client_request_id": "33333333-3333-4333-8333-333333333333"
}
```

Example `201 Created` response (illustrative IDs and users):

```json
{
  "status": true,
  "message": "Your document is with your reviewer.",
  "data": {
    "id": "11111111-1111-4111-8111-111111111111",
    "title": "Launch plan",
    "content": "Please review the proposed launch checklist.",
    "status": "pending",
    "submitter": {"id": "44444444-4444-4444-8444-444444444444", "name": "Jamie", "email": "jamie@example.com", "can_review": true},
    "assigned_reviewer": {"id": "22222222-2222-4222-8222-222222222222", "name": "Alex", "email": "alex@example.com", "can_review": true},
    "created_at": "2026-10-08T12:00:00Z",
    "decided_at": null,
    "file": null
  }
}
```

Approve with `{"decision":"approved","note":"Ready to launch."}` at `POST submissions/decision/{id}/`. A rejection without feedback returns `400`:

```json
{
  "status": false,
  "message": "Please check the highlighted fields.",
  "errors": {"note": ["Add a reason so the submitter knows what needs fixing."]}
}
```

Success responses use `{status: true, data?, message?}`; failures use `{status: false, message, errors?}`. Lists contain summary records; detail adds `content`. A file submission returns `file: {name, size, content_type}` instead of `null`.

Creation returns `201`, successful retries/reads return `200`, and OTP/upload-validation dispatch returns `202`. Errors distinguish invalid input (`400`), invalid login (`401`), denied access/session/CSRF (`403`), inaccessible records (`404`), conflicting requests or decisions (`409`), expired uploads (`410`), rate limits (`429`), and temporary provider failures (`503`).

**Why this contract:** explicit create/decision operations match the UI and keep state transitions in one service path. Separating file transfer from submission keeps large bytes out of API requests and ensures only validated uploads attach. A consistent envelope gives the frontend one error-handling pattern; pagination bounds list responses.

## Data model and key decisions

| Model | Purpose and relationships |
|---|---|
| `User` | Verified identity; can submit and review assigned work. |
| `RegistrationChallenge` / `AuthRateLimit` | Pending registration with hashed password/OTP, expiry and attempts; persistent abuse counters. |
| `Submission` | Links one submitter and one reviewer; stores text or private-file metadata and current status. |
| `DocumentUpload` | Belongs to an owner; tracks validation and attaches to at most one submission. |
| `SubmissionEvent` | Belongs to a submission and actor; records submission and decision history. |

- **State machine:** `pending → approved` or `pending → rejected`; both outcomes are final. Self-review is prohibited. Content and reviewer assignment remain fixed so the decision always refers to the submitted version.
- **Atomic changes and safe retries:** submission, attachment, and history commit together. A client-generated request UUID plus a payload hash prevents duplicate creates; reusing it with different content returns `409`. PostgreSQL row locks serialize decisions. Identical decision retries return the recorded result; conflicting decisions return `409`.
- **Session authentication:** Django's database-backed sessions provide revocation and HttpOnly cookies without adding a JWT refresh-token lifecycle. CSRF protection covers browser writes. Account creation happens only after OTP verification.
- **Modular monolith and database queue:** service modules keep domain logic separate while sharing transactions. The upload worker uses durable PostgreSQL records, leases, and retries, avoiding another broker for this scope. SQLite makes local setup easy but does not establish production concurrency behavior.
- **Scope trade-offs:** one team, one reviewer, and immutable submissions keep the core approval flow focused. Email sends synchronously; DOCX conversion runs on first preview and is cached. Background email delivery, isolated conversion, and richer approval workflows are deferred.

## Checks

For the local development tools, install Python 3.12+ and Node 24+, then run:

```bash
make setup
make test             # Backend, frontend tests, TypeScript, and production build
make test-postgres    # Includes PostgreSQL concurrency checks; requires Docker
make test-e2e         # Desktop/mobile journeys, including real Swagger Try it out
```

The latest deployed release passed **89 backend tests against PostgreSQL with no skips**, including real DOCX conversion, plus **10 frontend tests**, the production build, and **10 desktop/mobile browser journeys**, including Swagger. Live checks verified Azure uploads, previews, access isolation, approval, and email OTP login. GitHub Actions is configured to run automated checks on pushes and pull requests.

Validate the OpenAPI document locally with `bash scripts/backend.sh spectacular --validate --fail-on-warn`. The Swagger browser test signs in, creates a submission, checks unrelated-user isolation, validates rejection feedback, and approves as the assigned reviewer using the UI controls.

## Future product scope

- **Multiple reviewers per document:** support parallel or sequential reviews, with clear rules for when a document is approved or rejected.
- **Admin panel:** manage documents, reviewer eligibility, and assignments, with role-based access and an audit trail for changes.
- **Stats dashboard:** track submission volume, pending reviews, approval/rejection rates, turnaround time, and reviewer workload.

These are planned extensions; the current version supports one reviewer per submission and basic status summaries.

## Production readiness

The deployed app already has HTTPS, private storage, managed identity, rate limits, and database backups. For broader use, I would add monitored uptime/error alerts, reliable background email delivery and improved inbox placement, account recovery, workspace isolation, malware scanning, and isolated background preview conversion. The current single-VM deployment would also need database high availability and routine restore drills.

## AI tools used

**Codex** assisted with product planning, frontend/backend scaffolding, service and UI implementation, test writing, debugging, Azure integration, and deployment. The local `akshit-backend` and `beautiful-websites` skills guided code structure and visual direction. Validation included automated tests and real upload, preview, approval, and OTP checks.
