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
| New M6 (your real week) and M7 (visual refresh), from the owner's feedback after using M5; production readiness becomes M8 and optional extensions M9 | Shifts and plans were hard to find, school deadlines lived in another calendar, and the look needed warmth |

## Milestones

### M1: Foundation — Done
Repository, Docker Compose, configuration, logging, errors, full schema and migration, authentication,
application shell. Requirements: K1, K2 (schema), K3 (storage), K4, K5, K6.

### M2: Academic Management — Done
Course, task, availability and preference APIs and screens. B1–B3, C1–C3, D1–D4.
**Done when:** every endpoint has validation and cross-user isolation tests, and a user can enter a
real semester through the UI.

### M3: Scheduling Engine — Done
Timeline, DST handling, feasibility analysis, pacing, guarded greedy, explanations, adapter service,
preview and apply, list view. E1–E5.
**Done when:** every invariant in `SCHEDULING_ENGINE.md` §10 passes on hand-written and generated
scenarios, and a benchmark records planning time.

### M4: Adaptive Planning and Manual Control — Done
Repair algorithm, event triggers, missed-session reconcile, proposal diffs, accept and reject, move,
resize, lock, conflict detection, alternatives. F1–F3, J1–J8 (API).
**Done when:** each event type in the design has a test showing minimal change, and locked sessions
never move.

### M5: Calendar, Dashboard, Tracking, Analytics — Done
Calendar with drag and resize, proposal review screen, study timer, dashboard, charts. A1–A5, G1–G3,
H1–H2, J1–J2 (UI). Begins with a short spike on calendar time zone behavior.
**Done when:** all figures trace to real data, with loading, empty and error states on every screen.

### M6: Your Real Week — Done
Busy times with kinds, shown on the calendar and added by dragging; calendars connected by link;
deadline suggestions. L1–L4.
**Done when:** a student's classes, shifts and plans all shape the schedule, and a school calendar
link stays in sync without creating anything the student did not confirm.

### M7: Visual Refresh — Done
A warmer dark theme and a light theme, switchable from the sidebar and in Settings (match device,
light, dark). Every screen checked in both.
**Done when:** both themes pass WCAG AA contrast for every text pairing, enforced by a test.

**Second pass, from the owner's feedback that the look could still improve:** each course's colour
now carries through the app (calendar sessions, task badges, course cards with a colour band and
initials). Deadlines show how soon they are ("Due tomorrow", "In 3 days", "Overdue"), counted in
calendar days in the profile's zone. The dashboard header shows a ring for how much of this
week's study is done and the next deadline. Task rows show progress against the estimate, with icon
actions. "Your week" opens with a week-at-a-glance picture and the free study hours per day.

### M8: Production Readiness — Not started
Notifications, rate limiting, security review, Playwright journeys, performance pass, production
images, deployment, documentation. A6, I1–I3, K7.
**Done when:** the application runs at a public URL through a CI-driven deployment.

### M9: Optional Extensions — Not started
CP-SAT comparison against the baseline. Optional AI helper that is off by default and never required.
Only after M8.

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

**CI:** the GitHub Actions workflow passed on its first run, for the M1 code.

### M2 verification record (2026-11-10)

| Check | Result |
|-------|--------|
| Backend tests against real PostgreSQL 17 | 255 passed |
| Ruff lint and format, mypy strict | Clean |
| Frontend tests (stubbed server) | 81 passed |
| ESLint, TypeScript, production build | Clean |
| Migration applied to the existing M1 database through Docker Compose | Passed |
| Every private route rejects anonymous requests, using a route list read from the app | 25 routes |
| Every record-by-ID route returns 404 to another user and leaves the record unchanged | 11 routes |
| Removing the ownership check as a deliberate bug | 11 isolation tests failed, as they should |
| Manual browser journey on the real stack, as a user in `Asia/Tokyo` | Course, exam with correct UTC deadline, progress logging, course totals, overlap error, weekly hours and commitment saved after reload |

### M3 verification record (2026-11-10)

| Check | Result |
|-------|--------|
| Backend tests against real PostgreSQL 17 | 1885 passed |
| Engine invariants on 500 generated scenarios, 8 time zones, daylight saving changes | Passed |
| Determinism, including shuffled input order | Passed on all 500 |
| "If plain EDF meets every deadline, so does the plan" | Passed on all 500; a guard test confirms both outcomes occur |
| Benchmark | 60 tasks: 0.26 s over 28 days, 0.48 s over 120 days |
| Deliberately introduced bugs (9 in the engine, 5 in preview and apply) | Each caused failures |
| Frontend tests (stubbed server), lint, types, build | 91 passed, clean |
| Manual browser journey on the real stack | Six tasks including impossible and overdue ones; preview, apply, reload, regenerate |

The browser journey found two bugs that automated tests had missed, both now fixed and covered: a
reserved logging field crashed previews, because tests ran below `INFO` level, and one impossible task
removed every other task's early-finish margin.

### M4 verification record (2026-11-10)

| Check | Result |
|-------|--------|
| Backend tests against real PostgreSQL 17, also inside the Docker image | 4984 passed, 99% coverage |
| Frontend tests (stubbed server), lint, types, build | 102 passed, clean |
| Benchmark: repairing 288 sessions after losing a weekday | 0.2 s, 44 changes |
| Each event type has a test showing a minimal change | Missed, overrun, early finish, new exam, deadline earlier and later, lost availability, new block, lower limit |
| Repair and rebuild obey every rule on 500 generated scenarios | Passed |
| Locked sessions never change | Passed on all 500, for repair and rebuild |
| Repairing a repaired schedule changes nothing | Passed on all 500 |
| Repair loses no more work than a rebuild | Passed on all 500 |
| Deliberately introduced bugs (6 in repair and placement, 6 in the API) | Each caused failures |
| Manual browser journey on the real stack | Missed session gave 1 added and 7 unchanged; conflict showed suggested times; locked and edited sessions stayed through an availability change that moved the other 6 |

The generated scenarios found two real bugs during development: repeated updates kept adding sessions
for open-ended work, and a session could be both shortened and removed in one proposal.

### M5 verification record (2026-11-10)

| Check | Result |
|-------|--------|
| Backend tests against real PostgreSQL 17, also inside the Docker image | 5054 passed, 99% coverage |
| Ruff lint and format, mypy strict | Clean |
| Frontend tests (stubbed server), lint, types, production build | 150 passed, clean |
| Every new route rejects anonymous requests and returns 404 to another user | Covered by the isolation tests, which read routes from the app |
| Figures trace to records | Each dashboard and analytics figure is asserted against records the test created; a new account returns zeros |
| Local days and weeks | Work is split at local midnight, including across a week boundary and the 25-hour day |
| Real FullCalendar conversion at clock changes | Contract test on the repeated hour and the skipped hour |
| Deliberately introduced bugs (4 in the timer, 5 in analytics, 1 in the daily limit) | Each caused failures |
| Manual browser journey on the real stack | Real mouse drag and resize; a refused drop put the session back and offered times; a drop on a 2:30 AM that does not exist saved as 3:00 AM; timer survived a reload and held while paused; finished time reached the dashboard and charts; a Tokyo profile in a Toronto browser showed Tokyo times; phone layout has no sideways scroll |

The spike found that FullCalendar's time conversion contradicts our rules at clock changes, which is
why the calendar converts dropped times itself. See `ARCHITECTURE.md` section 8.

### M6 verification record (2026-11-10)

| Check | Result |
|-------|--------|
| Backend tests against real PostgreSQL 17, also inside the Docker image | 5155 passed, 99% coverage |
| Frontend tests (stubbed server), lint, types, production build | 165 passed, clean |
| Migration: upgrade, downgrade, upgrade; models match | Passed |
| Calendar parsing | Weekly lectures across a clock change with an exception, Moodle due items, floating and named zones, all-day, cancelled and free events, malformed files |
| Fetcher safety | Private, loopback, link-local, metadata, shared and IPv4-mapped addresses refused; redirects re-checked; size cap; error statuses |
| New routes protected and isolated | Covered by the isolation tests, plus a test that busy times never include another student's |
| Deliberately introduced bugs (3 in fetching, 2 in parsing, 8 in feeds and busy times) | Each caused failures, after adding one test the first round showed was missing |
| Real network | A public Google holidays calendar imported over HTTPS through the pinned connection (all-day events correctly skipped); links to localhost and the metadata address refused |
| Manual browser journey on the real stack | Busy times listed with kinds; lecture drawn striped on the calendar; a shift added by dragging across Thursday; a calendar deadline reviewed and added as a task |

The browser journey found a crash the mocked tests could not: the preview FullCalendar draws while
you drag across empty time has no session, and the renderer assumed one. With no error boundary,
the whole app went blank. Both are fixed and tested, and a page crash now leaves the menu usable.

### M7 verification record (2026-11-10)

| Check | Result |
|-------|--------|
| Frontend tests, lint, types, production build | 210 passed, clean |
| Contrast, read from the real stylesheet | Every text pairing meets WCAG AA (4.5:1) in both themes; 40 checks |
| Theme choice | Follows the device by default; an explicit choice wins and is remembered; set before first paint, so no flash |
| Manual browser check, both themes | Login, dashboard, schedule calendar with busy times, analytics charts, Your week, tasks, settings; phone width has no sideways scroll |

The check found a bug older than this milestone: course colour dots inside text rows had no size
and were invisible. Fixed. Fade-ins appear paused in a hidden browser pane, which is the browser
saving work, not a fault; they run normally on screen and not at all with reduced motion.

**Calendar follow-up, from the owner's use:** midterms entered as tasks never appeared on the
calendar, because it drew only study sessions and busy times, and the owner had no weekly study
hours, so nothing had been scheduled. Deadlines and exams now sit in a "Due" row on their local day
(exams drawn stronger; clicking one edits the task), there is a month view, and the Schedule page
says plainly when no study hours are set. Calendar titles from eClass with HTML entities
("&amp;amp;") are now decoded on import. Covered by new tests; each was checked to fail when the
behaviour it guards was broken on purpose.

**Layout follow-up, from the owner's use:** the desktop sidebar folds down to an icon rail (button
at its top, or Ctrl/⌘ + \\), remembered per device; links keep their names for screen readers and
show them on hover. The schedule calendar no longer scrolls inside the page: it draws only the hours
in use (study hours, busy times and sessions on screen, an hour either side, never less than 8 AM to
10 PM) at their natural height, with the day headers pinned while the page scrolls. The nested
scroll box was what made scrolling feel wrong. Folding the sidebar exposed a FullCalendar sizing bug
(it re-measures only on window resize); the calendar now watches its own box.

**Second pass check (2026-11-10):** 235 frontend tests passed; lint, types and build clean. New
tests cover the due labels (another zone and the day clocks went back), free hours per day, the
dashboard header figures, and that ink text stays at 4.5:1 on a wash of any course colour, from
black to white, in both themes. Dashboard, tasks, courses, a course page, the calendar and Your week
were checked in the browser in both themes, and tasks at phone width; that caught a misplaced
time-axis label and a progress bar squeezed to nothing on phones, both fixed.

**Known gaps carried forward:**
- The theme is saved per device, not per account. A preference column can be added if wanted.
- Untested against a real YorkU eClass link, which needs the owner's account. The format it uses is covered by tests.
- Calendar links are stored unencrypted (M8).
- Login rate limiting is not implemented (M8).
- Docker images are for development. Production images are in M8.
- Missed sessions are detected when the schedule is opened, not at the moment they are missed (by design; see `PRD.md`).
- There is no Playwright suite yet (M8). The browser journeys above were run by hand.
- Touch dragging on a real phone has not been tested. The list view and the Change form work without dragging.
- A timer running past its planned end does not reserve the time after it, so a new plan could schedule a session during the overrun.
- Deleting a task also deletes its study history, so past charts lose that time.
- Scoring weights are reasoned starting values and have not been tuned against data (M9).
- The notification table exists and its constraints are tested, but no API uses it yet (M8).
