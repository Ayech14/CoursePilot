# CoursePilot — Development Roadmap

Status values mean exactly this: **Done** is implemented and tested. **In progress** is partly
built. **Not started** is not built. Requirement IDs refer to `PRD.md`.

## Changes from the original milestone plan

| Change | Why |
|--------|-----|
| Manual schedule control is split: API in M4, drag and drop in M5 | The logic belongs with rescheduling; the interaction belongs with the calendar |
| M3 includes saving and previewing a schedule, with a simple list view | Otherwise engine results could not be seen until M5 |
| The full schema is built in M1 | Its constraints shape every later feature and should be proven early |
| New optional M7 | Keeps CP-SAT and AI from competing with the core product |

## Milestones

### M1: Foundation — Done
Repository, Docker Compose, configuration, logging, errors, full schema and migration, authentication,
application shell. Requirements: K1, K2 (schema), K3 (storage), K4, K5, K6.

### M2: Academic Management — Not started
Course, task, availability and preference APIs and screens. B1–B3, C1–C3, D1–D4.
**Done when:** every endpoint has validation and cross-user isolation tests, and a user can enter a
real semester through the UI.

### M3: Scheduling Engine — Not started
Timeline, DST handling, feasibility analysis, pacing, guarded greedy, explanations, adapter service,
preview and apply, list view. E1–E5.
**Done when:** every invariant in `SCHEDULING_ENGINE.md` §10 passes on hand-written and generated
scenarios, and a benchmark records planning time.

### M4: Adaptive Planning and Manual Control — Not started
Repair algorithm, event triggers, missed-session reconcile, proposal diffs, accept and reject, move,
resize, lock, conflict detection, alternatives. F1–F3, J1–J8 (API).
**Done when:** each event type in the design has a test showing minimal change, and locked sessions
never move.

### M5: Calendar, Dashboard, Tracking, Analytics — Not started
Calendar with drag and resize, proposal review screen, study timer, dashboard, charts. A1–A5, G1–G3,
H1–H2, J1–J2 (UI). Begins with a short spike on calendar time zone behavior.
**Done when:** all figures trace to real data, with loading, empty and error states on every screen.

### M6: Production Readiness — Not started
Notifications, rate limiting, security review, Playwright journeys, performance pass, production
images, deployment, documentation. A6, I1–I3, K7.
**Done when:** the application runs at a public URL through a CI-driven deployment.

### M7: Optional Extensions — Not started
CP-SAT comparison against the baseline. Optional AI helper that is off by default and never required.
Only after M6.

## Status notes

### M1 verification record (2026-11-09)

| Check | Result |
|-------|--------|
| Backend tests against real PostgreSQL 17 (local venv and inside the Docker image) | 103 passed, 99% line coverage |
| Ruff lint and format, mypy strict | Clean |
| Frontend tests (Vitest and Testing Library, with a stubbed server) | 22 passed |
| ESLint, TypeScript, production build | Clean |
| Alembic: upgrade, downgrade, upgrade; models match migrations | Passed |
| `docker compose up --build` from no images | All services healthy; migration applied |
| Manual browser journey on the real stack | Validation errors, register, reload keeps session, profile save, sign out, wrong password, sign in, mobile drawer |
| Tests catch deliberately introduced bugs (refresh reuse, password echo, single-flight refresh) | Each caused failures |

**Not verified:** the GitHub Actions workflow has not run, because nothing has been pushed.

**Known gaps carried forward:**
- Login rate limiting is not implemented (M6).
- Docker images are for development. Production images are in M6.
- Sidebar pages other than Dashboard and Settings are labeled "Not built yet".
- There is no Playwright suite yet (M6). The browser journey above was run by hand.
- The scheduler package is an empty, boundary-tested placeholder (M3).
- The schedule, timer, proposal and notification tables exist and their constraints are tested, but
  no API uses them yet.
