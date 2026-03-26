# PD3r Cloud Migration Plan

> **Created**: 2026-03-11
> **Status**: Planning
> **Author**: David Hook
> **Purpose**: Migrate PD3r from local development to VA cloud infrastructure

---

## Executive Summary

PD3r (Pete) has reached MVP with 899+ tests passing, Docker containerization, and comprehensive documentation. This plan covers the work needed to deploy to VA cloud infrastructure and hand off to another developer.

**Current state**: Runs locally via Docker Compose (backend + frontend + optional Postgres). Single-user, no authentication, no 508 compliance testing.
**Target state**: Cloud-hosted, multi-user with VA Enterprise ID, 508-compliant, CI/CD automated, production-hardened.

---

## Phase 1: Production Hardening (Pre-Cloud)

### 1.1 PostgreSQL Migration
**Current**: SQLite at `output/.sessions/checkpoints.db`
**Target**: PostgreSQL via `langgraph-checkpoint-postgres` (already in pyproject.toml)

Tasks:
- [ ] Update `session_manager.py` to use `AsyncPostgresSaver` when `DATABASE_URL` starts with `postgresql://`
- [ ] Uncomment and finalize PostgreSQL service in `docker-compose.yml`
- [ ] Add database migration/init script (checkpoint tables created automatically by LangGraph)
- [ ] Test session create, resume, and export against PostgreSQL
- [ ] Add connection pool settings (`pool_size`, `max_overflow`) to Settings

**Risk**: Low — LangGraph supports this natively, minimal code change.

### 1.2 Logging to stdout/stderr
**Current**: File-based logging to `output/logs/` (local JSONL traces + rotating API log)
**Target**: Structured JSON to stdout (12-factor app), cloud logging agent collects

Tasks:
- [ ] Add JSON log formatter for production mode (`ENVIRONMENT=production`)
- [ ] Redirect `logging` handlers to stdout when not in development
- [ ] Make local trace file logging conditional on `PD3R_TRACING=true` (already partially done)
- [ ] Remove `output/logs/` volume mount requirement for production

**Keep**: Local tracing (`PD3R_TRACING=true`) for development — it's valuable for debugging.

### 1.3 Health & Readiness Endpoints
**Current**: `GET /health` returns `{"status": "ok"}`
**Target**: Separate liveness and readiness probes

Tasks:
- [ ] `GET /health` — Liveness (lightweight, always returns 200 if process is up)
- [ ] `GET /ready` — Readiness: validates database connection, vector store loaded, API key present
- [ ] Return `503` from `/ready` if any dependency is unavailable

### 1.4 Security Hardening
Tasks:
- [ ] Lock down CORS origins via `PD3R_CORS_ORIGINS` env var (remove localhost defaults in production)
- [ ] Restrict `allow_methods` and `allow_headers` in CORS middleware to only what's needed
- [ ] Remove or gate the `POST /config` endpoint (runtime API key setting) — production should use env vars only
- [ ] Add request size limits to FastAPI
- [ ] Add rate limiting (e.g., `slowapi`) — per-user throttle + LLM cost budget per session

### 1.5 Frontend Configuration
**Current**: Nginx hardcodes backend as `http://pd3r:8000`
**Target**: Configurable backend URL

Tasks:
- [ ] Use `envsubst` in nginx entrypoint to template `BACKEND_URL` into `nginx.conf`
- [ ] Add `VITE_API_BASE_URL` for frontend API client (currently empty string)
- [ ] Ensure WebSocket URL is derived from the same base

---

## Phase 2: Enterprise ID & Multi-User Support

### Current State

PD3r has **zero** authentication. Any client can create, read, modify, or delete any session with only a session UUID. No user concept exists in the database, API models, or agent state.

**What's missing**:
- No user table or user_id on sessions
- No auth middleware on REST or WebSocket endpoints
- No login flow in frontend
- No audit trail of who did what
- No per-user session isolation

### 2.1 User Model & Session Ownership

Add user tracking to the data layer so sessions are tied to authenticated users.

Tasks:
- [ ] Add `user_id` and `created_by_email` fields to `pd3r_sessions` table
- [ ] Add `user_id: str | None` to `AgentState` in `src/models/state.py`
- [ ] Create `users` table: `user_id (PK), email, display_name, created_at, last_login`
- [ ] Update `SessionManager.create_session()` to accept and store `user_id`
- [ ] Add ownership check to all session endpoints: `GET`, `PATCH`, `DELETE`, `POST /messages`
- [ ] Filter `GET /sessions` (if added) to return only current user's sessions

### 2.2 Authentication Middleware

Add FastAPI dependency injection for auth. Support multiple identity sources to accommodate VA infrastructure.

Tasks:
- [ ] Create `src/api/auth.py` with `get_current_user()` dependency
- [ ] Support two auth modes (configurable via `PD3R_AUTH_MODE` env var):
  - **`header`** — Trust reverse proxy headers (`X-Remote-User`, `X-Remote-Email`) from VA SSOi
  - **`jwt`** — Validate Bearer token from OAuth2/OIDC flow (VA IAM / Keycloak)
- [ ] Add `PD3R_AUTH_ENABLED` toggle (default `false` for local dev, `true` for cloud)
- [ ] Protect all `/sessions/*` endpoints with `Depends(get_current_user)`
- [ ] Return `401` for unauthenticated requests, `403` for wrong session owner
- [ ] Add auth settings to `Settings`:
  ```
  auth_enabled: bool = False
  auth_mode: str = "header"  # "header" or "jwt"
  jwt_secret: str = ""
  jwt_algorithm: str = "RS256"
  ```

### 2.3 WebSocket Authentication

WebSocket connections are currently unauthenticated. Anyone who knows a session UUID can connect.

Tasks:
- [ ] Validate auth token during WebSocket handshake (before `websocket.accept()`)
- [ ] For `header` mode: extract identity from initial HTTP headers
- [ ] For `jwt` mode: accept token as query parameter (`?token=...`) or first message
- [ ] Verify connecting user owns the session
- [ ] Reject with `4001` (unauthorized) or `4003` (forbidden) close codes

### 2.4 VA Enterprise ID Integration

VA uses **SSOi** (legacy, header-based) and is migrating to **VA IAM** (OAuth2/OIDC). Support both.

**Option A: SSOi (Reverse Proxy Headers)**
- VA's SSOi reverse proxy sets `X-Remote-User` and `X-Remote-Email` headers
- No application-level login flow needed — proxy handles authentication
- App just reads and trusts the headers
- Simplest to implement; works behind VA's existing infrastructure

**Option B: OAuth2/OIDC (VA IAM)**
Tasks:
- [ ] Add `authlib` dependency for OAuth2 client
- [ ] Create `/auth/login` → redirect to VA IAM authorize endpoint
- [ ] Create `/auth/callback` → exchange code for tokens, set secure HttpOnly cookie
- [ ] Create `/auth/logout` → clear session cookie
- [ ] Add `va_oauth_client_id`, `va_oauth_client_secret`, `va_oauth_metadata_url` to Settings
- [ ] Store access token in secure HttpOnly cookie (not localStorage)

**Frontend Login Flow**:
- [ ] Add `useAuth` hook: checks auth state, provides login/logout
- [ ] Add login page or redirect (before session creation)
- [ ] Display user name/email in header
- [ ] Include auth token in API requests (`Authorization: Bearer ...` or cookie)
- [ ] Clear local state on logout

### 2.5 Audit Trail

Required for VA compliance (ATO). Every action must be attributable to a user.

Tasks:
- [ ] Create audit log table: `timestamp, user_id, action, session_id, details`
- [ ] Log: session creation, message sends, field overrides, element actions, exports
- [ ] Include user identity in all log entries (structured JSON format)
- [ ] Retain per VA records retention policy
- [ ] Consider immutable audit log (append-only, no deletes)

### 2.6 Multi-User Considerations

| Concern | Approach |
|---------|----------|
| Session isolation | user_id FK on sessions; ownership check on every endpoint |
| Concurrent access | Single owner per session (no shared editing in MVP) |
| Session listing | New `GET /sessions` endpoint filtered by current user |
| Session transfer | Future: admin can reassign session ownership |
| Data privacy | Users only see their own sessions, drafts, and exports |
| Rate limiting | Per-user throttle on session creation and message sends |

---

## Phase 3: Section 508 Compliance (WCAG 2.1 AA)

### Current State

The frontend uses radix-ui/shadcn primitives which provide a **solid accessibility foundation** — proper focus management, keyboard navigation, and semantic HTML in core components. However, the application layer has gaps that must be fixed before VA deployment.

**Strengths** (already working):
- Radix primitives handle accordion, dialog, tabs, tooltip keyboard navigation
- Focus-visible rings on all interactive components
- `sr-only` text on dialog close buttons
- VA logo has descriptive alt text
- Form inputs have proper label associations
- `lang="en"` on HTML root

**Gaps** (must fix):

### 3.1 Critical: Screen Reader Announcements (aria-live)

Chat messages, agent responses, and status changes arrive via WebSocket but are invisible to screen readers.

Tasks:
- [ ] Add `aria-live="polite"` to `MessageList` container (`frontend/src/components/chat/MessageList.tsx`)
- [ ] Add `role="status"` and `aria-label="Agent is typing"` to `TypingIndicator`
- [ ] Add `aria-live="polite"` to ProductPanel status area for element updates
- [ ] Ensure toast notifications (sonner) announce to screen readers

### 3.2 Critical: Icon-Only Buttons Need Labels

Many buttons use only icons (checkmark, lock, edit, regenerate) with no accessible name.

Tasks:
- [ ] Add `aria-label` to all icon-only buttons in `ProductPanel.tsx`:
  - Approve button: `aria-label="Approve section"`
  - Lock/unlock: `aria-label="Lock section"` / `aria-label="Unlock section"`
  - Edit: `aria-label="Edit section"`
  - Regenerate: `aria-label="Regenerate section"`
- [ ] Add `aria-label` to icon buttons in `PhaseAccordion.tsx` (move, delete org levels)
- [ ] Add `aria-label` to header icon buttons (settings, history, theme toggle)

### 3.3 Critical: Keyboard Accessibility

Some interactive elements use `<div>` or `<span>` with `onClick` instead of `<button>`, making them unreachable by keyboard.

Tasks:
- [ ] Convert mission text display `<div onClick>` to `<button>` in `PhaseAccordion.tsx`
- [ ] Convert word count target `<span onClick>` to `<button>` in `ProductPanel.tsx`
- [ ] Ensure all `onClick` handlers also respond to Enter/Space key events
- [ ] Verify tab order is logical through chat input → message list → draft panel

### 3.4 Major: Semantic Landmarks & Navigation

Tasks:
- [ ] Wrap main content area in `<main>` tag (`AppShell.tsx`)
- [ ] Add `aria-label="Workflow progress"` to sidebar `<aside>`
- [ ] Add `aria-label="Chat messages"` to chat ScrollArea
- [ ] Add `aria-label="Position description draft"` to ProductPanel ScrollArea
- [ ] Add `aria-current="step"` to current phase in PhaseAccordion
- [ ] Consider skip-to-content link: "Skip to chat" at page top

### 3.5 Major: Decorative Elements

Tasks:
- [ ] Add `aria-hidden="true"` to decorative icons: chevrons, spinners, status dots
- [ ] Add `aria-label` to status dots that convey meaning (e.g., `aria-label="Status: approved"`)
- [ ] Ensure Loader2 spinner icons are hidden from screen readers

### 3.6 Moderate: Color Contrast Verification

The VA blue (#003F72) and VA red color system uses OKLCH perceptual values, but specific combinations need verification.

Tasks:
- [ ] Audit all text/background combinations against WCAG AA (4.5:1 normal, 3:1 large text)
- [ ] Specific concerns:
  - Muted foreground on muted background (sidebar text)
  - Opacity-based text in header (may fail contrast)
  - Dark mode muted-foreground combinations
- [ ] Adjust OKLCH values where contrast fails
- [ ] Document verified contrast ratios

### 3.7 Moderate: Form Accessibility

Tasks:
- [ ] Add `aria-label` to word count target inline edit input
- [ ] Add `aria-describedby` for error states on form inputs
- [ ] Ensure focus moves to first error field on validation failure
- [ ] Label all textarea elements (notes field in ProductPanel)

### 3.8 Testing & Validation

Tasks:
- [ ] Run axe-core automated scan (install `@axe-core/react` or browser extension)
- [ ] Test with VoiceOver (macOS) — complete interview + draft review workflow
- [ ] Test with NVDA (Windows) if available
- [ ] Keyboard-only navigation test: complete full workflow without mouse
- [ ] Document results and remaining issues
- [ ] Consider adding `eslint-plugin-jsx-a11y` to catch issues at dev time

### 508 Effort Estimate

| Priority | Items | Effort |
|----------|-------|--------|
| Critical (3.1-3.3) | aria-live, icon labels, keyboard | 2-3 days |
| Major (3.4-3.5) | landmarks, decorative elements | 1-2 days |
| Moderate (3.6-3.7) | contrast, forms | 1-2 days |
| Testing (3.8) | automated + manual verification | 1-2 days |
| **Total** | | **5-9 days** |

---

## Phase 4: Cloud Infrastructure (was Phase 2)

### 2.1 Container Registry
Tasks:
- [ ] Set up container registry (ECR, ACR, or GCR depending on VA cloud provider)
- [ ] Create build pipeline to push tagged images on merge to main
- [ ] Tag images with git SHA + semantic version

### 2.2 Infrastructure as Code
Tasks:
- [ ] Choose IaC tool (Terraform recommended for multi-cloud flexibility)
- [ ] Define resources:
  - Container orchestration (ECS, AKS, or GKE)
  - PostgreSQL managed instance (RDS, Azure Database, Cloud SQL)
  - Load balancer with WebSocket support (sticky sessions)
  - Container registry
  - Secret management (Secrets Manager, Key Vault, etc.)
  - Logging/monitoring service
  - DNS entry
- [ ] Create separate environments: `dev`, `staging`, `production`
- [ ] Store IaC in `infra/` directory (or separate repo per VA policy)

### 2.3 Kubernetes Manifests (if using K8s)
```
infra/k8s/
├── namespace.yaml
├── backend/
│   ├── deployment.yaml
│   ├── service.yaml
│   ├── configmap.yaml
│   └── hpa.yaml          # Horizontal Pod Autoscaler
├── frontend/
│   ├── deployment.yaml
│   └── service.yaml
├── ingress.yaml           # With WebSocket annotations
├── secrets.yaml           # Reference to external secret store
└── postgres/              # Only if self-managing (prefer managed DB)
```

Key considerations:
- **WebSocket sticky sessions**: Ingress must route by session affinity (cookie or IP)
- **Vector store**: Mount as read-only volume or bake into container image
- **Secrets**: Use external-secrets-operator to sync from cloud KMS

### 2.4 Secret Management
**Current**: `.env` file with `OPENAI_API_KEY`
**Target**: Cloud-native secret management

Secrets to manage:
| Secret | Source | Notes |
|--------|--------|-------|
| `OPENAI_API_KEY` | Cloud KMS | Required |
| `DATABASE_URL` | Cloud KMS | PostgreSQL connection string |
| `LANGCHAIN_API_KEY` | Cloud KMS | Optional (LangSmith tracing) |
| `JWT_SECRET` | Cloud KMS | Required if `auth_mode=jwt` |
| `VA_OAUTH_CLIENT_SECRET` | Cloud KMS | Required if using OAuth2/OIDC |

---

## Phase 5: CI/CD Pipeline

### 3.1 GitHub Actions
```yaml
# .github/workflows/ci.yml
on:
  push:
    branches: [main]
  pull_request:
    branches: [main]

jobs:
  test:
    - poetry install
    - poetry run pytest -q
    - cd frontend && npx tsc --noEmit
    - cd frontend && npx vite build

  build:
    needs: test
    - docker build -t pd3r-backend .
    - docker build -t pd3r-frontend frontend/
    - push to container registry (on main only)

  deploy:
    needs: build
    if: github.ref == 'refs/heads/main'
    - deploy to staging
    - (manual gate for production)
```

Tasks:
- [ ] Create `.github/workflows/ci.yml` — lint + test + type-check
- [ ] Create `.github/workflows/deploy.yml` — build + push + deploy
- [ ] Add branch protection on `main` (require CI pass, 1 approval)
- [ ] Set up GitHub Environments for staging/production with approval gates

### 3.2 Pre-commit Hooks
Tasks:
- [ ] Add `pre-commit` config (ruff lint, ruff format, pytest smoke tests)
- [ ] Frontend: ESLint + TypeScript check

---

## Phase 6: Monitoring & Observability

### 4.1 Application Monitoring
Tasks:
- [ ] Integrate with VA's monitoring stack (CloudWatch, Datadog, or Prometheus/Grafana)
- [ ] Key metrics to track:
  - Request latency (p50, p95, p99)
  - WebSocket connection count
  - LLM call latency and token usage
  - Error rate by endpoint
  - Active sessions
- [ ] Set up alerts: error rate > 5%, latency p95 > 10s, LLM API failures

### 4.2 Cost Tracking
- OpenAI API costs are the primary operating expense (~$0.50-$1.00 per PD)
- LangSmith provides built-in LLM cost tracking if enabled
- Local tracing already captures token counts and cost estimates per call

### 4.3 Audit Logging
- [ ] Log all session creation, message sends, and document exports
- [ ] Structured audit log format for compliance (who, what, when)
- [ ] Retain audit logs per VA retention policy

---

## Phase 7: Scaling Considerations

### Single-Replica (MVP Cloud)
Sufficient for initial deployment:
- 1 backend container + 1 frontend container
- Managed PostgreSQL (smallest tier)
- Handles ~10-20 concurrent users

### Multi-Replica (Scale-Out)
Required changes for horizontal scaling:
1. **PostgreSQL** for shared state (Phase 1.1)
2. **Sticky sessions** on load balancer (WebSocket affinity)
3. **Shared vector store** — either:
   - Bake into container image at build time (simplest, immutable per deploy)
   - Mount as read-only shared volume (if using K8s PersistentVolume)
   - Migrate to managed vector DB (Pinecone, Weaviate) — overkill for current scale
4. **Redis** for session affinity cache (only if needed)

### Estimated Resource Requirements
| Component | CPU | Memory | Storage |
|-----------|-----|--------|---------|
| Backend (per replica) | 0.5-1 vCPU | 512MB-1GB | — |
| Frontend (per replica) | 0.25 vCPU | 128MB | — |
| PostgreSQL | 1 vCPU | 2GB | 10GB |
| Vector Store | Baked in | ~60MB in container | — |

---

## Architecture: Current vs. Cloud

```
CURRENT (Local)
┌─────────┐     ┌──────────┐     ┌────────┐
│ Browser  │────▶│ Vite Dev │────▶│ FastAPI│──▶ SQLite
│          │     │ :5175    │     │ :8000  │──▶ ChromaDB (local)
└─────────┘     └──────────┘     └────────┘──▶ OpenAI API

CLOUD (Target)
┌─────────┐     ┌──────────┐     ┌──────────────┐
│ Browser  │────▶│ VA SSOi  │────▶│ Nginx (SPA)  │
│          │     │ / IAM    │     └──────────────┘
│          │     │          │     ┌──────────────┐     ┌──────────┐
│          │     │ (sticky  │────▶│ FastAPI ×N   │────▶│ Postgres │
│          │     │  + auth) │     │ (auth middle │     │ (users + │
└─────────┘     └──────────┘     │  ware)       │     │  sessions)│
                                  │              │     └──────────┘
                                  │              │────▶ OpenAI API
                                  │ (vector store│────▶ Cloud Logging
                                  │  baked in)   │     (audit trail)
                                  └──────────────┘
```

---

## Risk Matrix

| Risk | Impact | Likelihood | Mitigation |
|------|--------|------------|------------|
| OpenAI API outage | High | Low | Architecture supports model swapping; queue retries |
| WebSocket drops behind LB | Medium | Medium | Sticky sessions + reconnection logic (already in frontend) |
| SQLite→Postgres data loss | High | Low | Test migration thoroughly; checkpoints are append-only |
| VA ATO delays | High | Medium | Containerized + auditable; start ATO process early |
| Single developer bus factor | High | High | This handoff plan; comprehensive docs + 899 tests |
| Cost overrun (LLM API) | Medium | Low | Usage tracking + budget alerts; ~$0.50/PD is very low |
| 508 compliance failure | High | Medium | Radix/shadcn foundation is strong; gaps are additive fixes, not architectural |
| SSO/IAM integration delays | High | Medium | Support both header-based (SSOi) and OAuth2 (IAM) to avoid blocking on either |
| Unauthenticated session access | High | High (current) | Phase 2 auth is prerequisite for any multi-user deployment |

---

## Handoff Checklist

See [handoff_checklist.md](handoff_checklist.md) for the developer handoff preparation checklist.

---

## Decision Log

| Decision | Choice | Rationale |
|----------|--------|-----------|
| Checkpointing | PostgreSQL (cloud) | LangGraph native support, no ORM needed |
| Vector store | Bake into container | Immutable knowledge base, simplest for deployment |
| Logging | stdout JSON | 12-factor, works with any cloud logging agent |
| Secret management | Cloud KMS | VA compliance, no secrets in code or env files |
| CI/CD | GitHub Actions | Already using GitHub; lightweight, well-documented |
| Container orchestration | TBD (depends on VA infra) | ECS, AKS, or GKE all supported |
| Authentication | Dual-mode (header + JWT) | SSOi uses proxy headers; VA IAM uses OAuth2/OIDC — support both |
| Session ownership | user_id FK on sessions | Simplest multi-tenant isolation; no shared sessions in MVP |
| 508 approach | Fix application layer | Radix/shadcn primitives are accessible; add aria-live, labels, landmarks |
| Accessibility testing | axe-core + VoiceOver + keyboard | Automated scan catches most issues; manual testing validates real workflows |
