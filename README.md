# CoursePilot

[![CI](https://github.com/Ayech14/CoursePilot/actions/workflows/ci.yml/badge.svg)](https://github.com/Ayech14/CoursePilot/actions/workflows/ci.yml)

A study planner that turns your courses, deadlines and free time into a realistic weekly schedule,
explains why each session is where it is, and adjusts the plan when your week changes.

**Live demo:** https://coursepilot-ko1s.onrender.com. Make an account with any email; nothing is sent
to it. The demo runs on free hosting, so the first visit after a quiet spell can take up to a
minute to load.

![The dashboard: today's progress against a daily goal, a study streak, recent sessions and a month overview](docs/screenshots/dashboard-dark.jpg)

## What it does

- **Plans your study time.** Add tasks with deadlines and effort estimates, set the hours you can
  study, and it builds a week of sessions that fits around classes and shifts. Each session says why
  it was placed there.
- **Adapts without starting over.** Miss a session, add an exam or finish early, and it proposes the
  smallest set of changes. You preview them and accept or reject each one.
- **Lets you take control.** Drag sessions to move or resize them, lock the ones that must not move,
  and get warned about clashes, with free slots suggested instead.
- **Tracks real effort.** A study timer records what you actually did. Analytics compare estimates
  with reality, show hours per course and week, and track a daily goal and study streak.
- **Knows your real week.** It works around classes, work shifts and plans. It can import a school
  calendar link (such as eClass) and suggests the deadlines it finds there.
- **Keeps you on track.** In-app notifications warn of deadlines, overdue work and schedule changes.
  Ctrl/⌘+K searches everything, and it has dark and light themes and works on phones.

## Screenshots

| | |
|---|---|
| ![Weekly schedule with study sessions, classes and a work shift](docs/screenshots/schedule-week.jpg) | ![Task list with due dates, course colours and progress](docs/screenshots/tasks.jpg) |
| **Schedule:** sessions planned around classes and a shift (striped), deadlines in the Due row | **Tasks:** due dates, priority and progress against the estimate |
| ![Analytics: weekly hours, hours per course, estimated against actual](docs/screenshots/analytics.jpg) | ![Quick search across tasks, courses and pages](docs/screenshots/search.jpg) |
| **Analytics:** built only from sessions you timed | **Search:** Ctrl/⌘+K from anywhere |
| ![Dashboard in the light theme](docs/screenshots/dashboard-light.jpg) | ![Your week: study hours and weekly commitments at a glance](docs/screenshots/your-week-light.jpg) |
| **Light theme** | **Your week:** free study time per day after classes and shifts |

<p align="center"><img src="docs/screenshots/phone-dashboard.jpg" alt="The dashboard on a phone" width="260"></p>

The screenshots show a demo student with made-up courses and study history.

## Try it in five minutes

The same steps work on the live demo or a local copy (see [Run it locally](#run-it-locally)).

1. **Create an account** and pick your time zone.
2. **Courses → New course.** Add one or two, for example "Linear Algebra".
3. **Tasks → New task.** Add an assignment or exam with a deadline in the next week or two and an
   effort estimate, such as 4 hours.
4. **Your week.** Use **Add time** to set the hours you can study on each day, then
   **Save weekly hours**. This step matters: without study hours there is nowhere to put sessions.
   Here you can also add busy times, such as a class or a shift.
5. **Schedule → Generate schedule.** Review the proposed sessions, each with a reason, and
   **Apply changes**.
6. **Use it.** Drag a session to a different time, press **Start timer** to time some study, then see
   the result on the **Dashboard** and in **Analytics**.

## Run it locally

You need [Docker](https://www.docker.com/products/docker-desktop/), and nothing else.

```bash
git clone https://github.com/Ayech14/CoursePilot.git
cd CoursePilot
docker compose up --build
```

The first build takes a few minutes. Then open:

| What | Where |
|------|-------|
| The app | http://localhost:5173 |
| API documentation (interactive) | http://localhost:8000/docs |
| PostgreSQL | `localhost:5433` (user, password and database are all `coursepilot`) |

Stop it with Ctrl+C, or `docker compose down`. Your data is kept in a Docker volume for next time;
`docker compose down -v` deletes it. If a port is taken, change it in a `.env` file (see
`.env.example`). The default credentials are for local use only.

## How it's built

- **Frontend:** React, TypeScript, Vite, Tailwind CSS, TanStack Query, FullCalendar.
- **Backend:** FastAPI, Pydantic, SQLAlchemy, PostgreSQL, Alembic.
- **Quality and delivery:** Pytest, Vitest, Playwright, Docker, GitHub Actions, Render, Neon.

Things worth a look:

- **A scheduling engine you can test.** A pure Python package with no database, so its guarantees
  are tested in isolation:
  - sessions never overlap;
  - daily limits are respected;
  - the same input always gives the same plan;
  - if plain earliest-deadline-first could meet every deadline, so does the plan.

  See [the engine design](docs/SCHEDULING_ENGINE.md).
- **Time zones and daylight saving done properly.** Weekly hours are wall-clock times, sessions are
  instants, and the two are converted in the student's own zone, including on the days the clocks
  change.
- **Rules the database enforces itself.** Constraints mean overlapping sessions or one student's
  task linked to another's course cannot be saved, even if the code has a bug.
- **Privacy and security.** Every student sees only their own data, and tests try to reach other
  students' records through every endpoint. Sign-in is rate limited, and calendar links are
  encrypted at rest. Pages have a strict Content-Security-Policy.
- **Tested.** About 5,200 backend tests (99% coverage) and 270 frontend tests. Playwright journeys run
  against the exact image that gets deployed.

The [architecture document](docs/ARCHITECTURE.md) explains the main decisions and the
alternatives that were weighed.

## Run the tests

**Backend.** Needs Python 3.14 and the database container (`docker compose up -d db`). The tests
create and delete their own `coursepilot_test` database.

```bash
cd backend
python3.14 -m venv .venv
.venv/bin/pip install -e ".[dev]"
.venv/bin/pytest
.venv/bin/ruff check . && .venv/bin/mypy
```

**Frontend.**

```bash
cd frontend
npm ci
npm test
npm run lint && npm run build
```

**Browser journeys (Playwright)**, against the production image:

```bash
# 1. Build the production image and give it an empty database.
docker build -t coursepilot .
docker compose up -d db
docker compose exec db createdb -U coursepilot coursepilot_e2e

# 2. Start it on port 8090.
docker run --rm -d --name coursepilot-e2e -p 8090:8000 \
  --add-host=host.docker.internal:host-gateway \
  -e DATABASE_URL=postgresql://coursepilot:coursepilot@host.docker.internal:5433/coursepilot_e2e \
  -e JWT_SECRET="$(openssl rand -base64 32)" \
  -e CALENDAR_LINK_KEY="$(openssl rand -base64 32)" \
  coursepilot
until curl -fs localhost:8090/health/ready; do sleep 1; done   # Wait for it to start.

# 3. Run the journeys, then stop the container.
cd e2e && npm ci && npx playwright install chromium && npx playwright test
docker stop coursepilot-e2e
```

GitHub Actions runs all three on every push (`.github/workflows/ci.yml`).

## Deploy your own

One Docker image serves both the API and the web app. It runs on Render's free plan, with
PostgreSQL on Neon's free plan. Pushes to `main` deploy automatically once CI passes. Setup takes
about ten minutes: [docs/DEPLOYMENT.md](docs/DEPLOYMENT.md).

## Documentation

| Document | Contents |
|----------|----------|
| [Product requirements](docs/PRD.md) | Features, requirement IDs, decisions on unclear cases |
| [Architecture](docs/ARCHITECTURE.md) | Layers, key decisions and alternatives, API, testing, risks |
| [Database design](docs/DATABASE_DESIGN.md) | Schema, constraints, indexes |
| [Scheduling engine](docs/SCHEDULING_ENGINE.md) | Algorithm, guarantees, rescheduling, manual control |
| [Roadmap](docs/DEVELOPMENT_ROADMAP.md) | Milestones, status, and a record of how each was verified |
| [Deployment](docs/DEPLOYMENT.md) | Hosting choice, one-time setup, everyday use |

## Status

Milestones 1 to 8 are done and deployed. Milestone 9, optional extensions such as comparing the
scheduler with a constraint solver, has not started. The [roadmap](docs/DEVELOPMENT_ROADMAP.md)
records what was built and how each milestone was checked.

## License

[MIT](LICENSE)
