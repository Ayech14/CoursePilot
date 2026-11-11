# CoursePilot

An academic planning platform that turns courses, deadlines and weekly availability into a realistic
study schedule, and adapts that schedule when plans change.

> **Status: Milestone 8 in progress.** Students can enter their semester, generate an explained
> study schedule, adapt it with minimal changes, drag and resize sessions on a calendar, time their
> study, see analytics built from their own records, add shifts and plans as busy time, connect
> a school calendar link, switch between dark and light themes, and get in-app notifications.
> Sign-in is rate limited and calendar links are encrypted at rest. Production deployment is not
> built yet. See [the roadmap](docs/DEVELOPMENT_ROADMAP.md) for exactly what is
> done and verified.

**Stack:** React, TypeScript, Vite, Tailwind CSS · FastAPI, Pydantic, SQLAlchemy · PostgreSQL, Alembic ·
Docker Compose, GitHub Actions

## Run it

Docker is the only requirement.

```bash
docker compose up --build
```

| Service | URL |
|---------|-----|
| Application | http://localhost:5173 |
| API documentation | http://localhost:8000/docs |
| PostgreSQL | `localhost:5433` (user, password and database are all `coursepilot`) |

The ports can be changed in a `.env` file; see `.env.example`. Default credentials are for local use only.

## Run the tests

The backend tests need the database container (`docker compose up -d db`). They create and destroy
their own `coursepilot_test` database.

```bash
cd backend
python3.14 -m venv .venv
.venv/bin/pip install -e ".[dev]"
.venv/bin/pytest
.venv/bin/ruff check .
.venv/bin/mypy
```

```bash
cd frontend
npm ci
npm test
npm run lint
npm run build
```

## Documentation

| Document | Contents |
|----------|----------|
| [Product requirements](docs/PRD.md) | Features, requirement IDs, resolved ambiguities |
| [Architecture](docs/ARCHITECTURE.md) | Layers, key decisions and alternatives, API, testing, risks |
| [Database design](docs/DATABASE_DESIGN.md) | Schema, constraints, indexes |
| [Scheduling engine](docs/SCHEDULING_ENGINE.md) | Algorithm, guarantees, rescheduling, manual control |
| [Roadmap](docs/DEVELOPMENT_ROADMAP.md) | Milestones, status, verification record |
