# CoursePilot — Product Requirements

## 1. Problem

University students juggle assignments, exams and readings across several courses. Calendars
record *when things are due* but do not answer *what should I work on now*, and a plan made
on Monday is stale by Wednesday. CoursePilot turns workload, deadlines and availability into
a realistic study schedule, and keeps that schedule valid as reality changes.

## 2. Target user

One student managing their own workload. There are no shared schedules, groups or
instructor roles.

## 3. Principles

1. **The algorithm is the product.** Scheduling is deterministic, testable and needs no
   external API. AI, if ever added, is optional and never decides the schedule.
2. **The user stays in control.** The engine proposes and the user decides. Nothing silently
   rewrites a schedule, and manual edits outrank automatic ones.
3. **Explain every decision.** Each placement carries a reason a student can read.
4. **Honest data.** Every number on screen comes from the user's real data.

## 4. Functional requirements

Requirement IDs are referenced by the roadmap so nothing can be silently dropped.

### A. Dashboard
| ID | Requirement | Milestone |
|----|-------------|-----------|
| A1 | Current courses, upcoming assignments and upcoming exams | M5 |
| A2 | Tasks that need attention | M5 |
| A3 | Today's study schedule | M5 |
| A4 | Weekly study hours; completed vs remaining tasks | M5 |
| A5 | Workload distribution | M5 |
| A6 | Important notifications | M8 |

### B. Courses
| ID | Requirement | Milestone |
|----|-------------|-----------|
| B1 | Create, edit, delete courses with description and color | M2 |
| B2 | Organize tasks by course | M2 |
| B3 | Course-specific progress and upcoming deadlines | M2 |

### C. Tasks (assignments and exams)
| ID | Requirement | Milestone |
|----|-------------|-----------|
| C1 | Types: assignment, project, midterm, final exam, quiz, reading, revision, general study | M2 |
| C2 | Fields: title, description, course, type, deadline, estimated effort, remaining effort, priority, status, actual time | M2 |
| C3 | Update task progress | M2 |

### D. Availability
| ID | Requirement | Milestone |
|----|-------------|-----------|
| D1 | Weekly available days and hours | M2 |
| D2 | Preferred session and break duration | M2 |
| D3 | Maximum daily study workload | M2 |
| D4 | Unavailable blocks, recurring and one-off | M2 |

### E. Scheduling engine
| ID | Requirement | Milestone |
|----|-------------|-----------|
| E1 | Consider deadlines, remaining work, priority, time to deadline, course balance | M3 |
| E2 | Respect availability, session length, daily maximum, breaks, existing sessions | M3 |
| E3 | No overlapping sessions; no unrealistic days | M3 |
| E4 | Understandable explanation for each decision | M3 |
| E5 | Deterministic baseline; evaluate constraint optimization later | M3, M9 |

### F. Adaptive rescheduling
| ID | Requirement | Milestone |
|----|-------------|-----------|
| F1 | React to missed sessions, overruns, new deadlines, early completion, availability changes | M4 |
| F2 | Preserve unaffected sessions | M4 |
| F3 | Preview changes before applying | M4 |

### G. Study sessions
| ID | Requirement | Milestone |
|----|-------------|-----------|
| G1 | Start, pause, resume, finish a session, with a timer | M5 |
| G2 | Record actual time; link sessions to tasks | M5 |
| G3 | Mark tasks complete; compare estimated vs actual | M5 |
| G4 | Start a timer on any open task without planning a session first | M8 |

### H. Analytics
| ID | Requirement | Milestone |
|----|-------------|-----------|
| H1 | Weekly hours, hours per course, completions over time | M5 |
| H2 | Workload distribution, estimated vs actual, upcoming workload, consistency | M5 |
| H3 | Today's study against an optional daily goal, the run of study days, recent sessions, and a month overview of time studied, tasks finished and deadlines | M8 |

### I. Notifications
| ID | Requirement | Milestone |
|----|-------------|-----------|
| I1 | Approaching deadlines, overdue and unfinished tasks | M8 |
| I2 | Schedule adjustments and workload conflicts | M8 |
| I3 | No repeated identical notifications | M8 |

### N. Getting around
| ID | Requirement | Milestone |
|----|-------------|-----------|
| N1 | Search pages, tasks and courses from the keyboard (Ctrl or ⌘ + K), without sending the query to the server | M8 |

### J. Manual schedule control
| ID | Requirement | Milestone |
|----|-------------|-----------|
| J1 | Move sessions between days and time slots | M4 (form), M5 (drag and drop) |
| J2 | Resize sessions | M4 (form), M5 (drag and drop) |
| J3 | Lock sessions against automatic moves | M4 |
| J4 | Regenerate while preserving locked sessions | M4 |
| J5 | Detect conflicts on manual change | M4 |
| J6 | Suggest alternative slots on conflict | M4 |
| J7 | Accept or reject proposed changes | M4 |
| J8 | Engine distinguishes automatic, manually modified and locked sessions | M4 |

### L. Your real week
| ID | Requirement | Milestone |
|----|-------------|-----------|
| L1 | Busy times with a kind (class, work shift, social, personal, other), weekly or once | M6 |
| L2 | Busy times visible on the schedule calendar, and added by dragging across it | M6 |
| L3 | Connect a calendar by link (iCalendar); its timed events become busy time and stay in sync | M6 |
| L4 | Due dates in connected calendars are suggested as tasks, created only when the student confirms | M6 |

### K. Platform
| ID | Requirement | Milestone |
|----|-------------|-----------|
| K1 | Authentication, secure password storage | M1 |
| K2 | Strict per-user data isolation | M1 (schema), every milestone (endpoints) |
| K3 | Time zone and DST correctness | M1 (storage), M3 (engine) |
| K4 | Validation, consistent errors, structured logs, env-based config | M1 |
| K5 | Migrations, indexes, API docs | M1 and ongoing |
| K6 | Unit and integration tests, CI | M1 and ongoing |
| K7 | Deployment | M8 |

## 5. Non-goals for v1

- Two-way calendar sync. CoursePilot reads calendar links (L3) but never writes to another calendar.
- Mobile apps. The web UI is responsive instead.
- Email or push delivery. Notifications are in-app (a bell in the sidebar), because email needs an external service.
- Multi-user collaboration and instructor roles.
- Multi-semester archives beyond archiving a course.

## 6. Ambiguities and how they were resolved

These are defaults, chosen so work can proceed. Each can be changed, and the cost of changing
it rises as later milestones build on it.

| # | Question | Decision | Reasoning |
|---|----------|----------|-----------|
| 1 | Are exams a separate entity? | No. An exam is a task whose deadline is its start time and whose effort is preparation time. | They share nearly every field and all scheduling behavior. |
| 2 | Must a task have a course? | No. `course_id` is optional, for general study. | The spec lists "general study tasks". |
| 3 | Must a task have a deadline? | No, except exams and quizzes. Undated tasks are planned last, with low urgency. | Readings and revision often have none, but an exam without a date cannot be planned for. |
| 4 | Do changes apply automatically? | Never. Events create a suggestion and the user previews and applies it. | F3 and J7 require user control. |
| 5 | When is a session "missed"? | A planned session that ended over 30 minutes ago and was never started. Reconciled when the user next loads their schedule. | Avoids needing a background worker. |
| 6 | Does moving a session lock it? | No. A moved session becomes *sticky*: kept whenever possible. Locking is a separate explicit action and is absolute. | Matches the spec's distinction between "modified" and "locked". |
| 7 | Can a manual move break soft rules? | Yes, with a warning: outside availability, over the daily limit, past the deadline. Overlap is always refused. | The student knows their life better than the rules do. Overlap is physically impossible. |
| 8 | Accept proposals whole or per change? | Both. Rejecting a single change is validated again, since it can cause a conflict. | J7 says "accept or reject proposed schedule changes". |
| 9 | Password reset and email verification? | Out of scope for v1. | Both need an email provider, and core features must not depend on external services. |
| 10c | Are overdue tasks scheduled? | No. They are reported as overdue until given a new deadline. | No session could meet a deadline that has passed, and silently treating it as "as soon as possible" would crowd out work that can still be on time. |
| 10d | Are tasks in archived courses scheduled? | No. | Archiving means the course is over. |
| 10a | Does logging the full estimate finish a task? | No. It keeps at least 15 minutes remaining until the student marks it finished or sets remaining effort to zero. | Time spent is not proof the work is done, and a task that runs long is an expected case. |
| 10b | Can tasks be added to an archived course? | No. Existing tasks keep their course. | Archiving means the course is over. |
| 10e | How many sessions can be open at once? | One, running or paused. | The database allows one running timer. Also limiting paused ones means no forgotten timer sits out of sight. |
| 10f | When can a session be started? | Any time on its local day, or later until it counts as missed. | Starting a little early is normal. Starting next week's session is a mistake. |
| 10g | What about a timer left running? | At finish the student can lower the time, but not raise it above what was timed. Lowering trims the work intervals. | Timed figures stay trustworthy. Untimed work has its own "log progress" action on the task. |
| 10h | Do hours logged by hand appear in weekly charts? | No. They count toward a task's actual time and the estimate comparison, but have no date. Charts say "timed sessions". | Inventing a date for them would make the weekly figures untrue. |
| 10i | When does a week start? | Monday, in the student's time zone. | Matches the availability grid. A preference can be added if anyone needs one. |
| 10j | Which calendar events block time? | Timed events. All-day events are skipped, and events marked free or cancelled are ignored. | School calendars use all-day events for holidays and notes. Blocking whole days for those would empty the schedule. |
| 10k | How is a deadline told apart from a class? | An event with no length (start equals end, or no end) is a deadline. | This is how Moodle (YorkU eClass) publishes "is due" items, and most course sites follow it. |
| 10l | Do calendar deadlines become tasks automatically? | No. They are suggested; the student confirms each and gives an estimate. | Chosen by the project owner. A calendar can hold many minor items, and only the student knows the effort. |
| 10m | How often do connected calendars sync? | When added, when the student asks, and when the schedule opens and a feed is over six hours old. | No background worker, the same approach as missed sessions. |
| 10n | What happens when a sync fails? | The last good events stay, and the error is shown on the feed. | A website being down for an hour should not erase a student's classes from their week. |
| 10 | What if the work cannot fit? | Plan as much as possible and report which tasks are at risk and by how many minutes. | An honest "this will not fit" is the most useful output in an overloaded week. |

## 7. Open questions for the project owner

1. **Deployment target** (M8). Options are a free PaaS tier or a small VPS with Docker Compose.
2. **Public demo** (M8). A seeded demo account would help a portfolio, but needs a reset job.
