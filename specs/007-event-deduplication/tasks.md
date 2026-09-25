# Tasks: Deduplicate events delivered through overlapping window requests

**Plan:** [./plan.md](./plan.md) · **Status:** done · **Date:** 2026-09-22

> Each task is a verifiable outcome (a test, an endpoint, a migration), not an
> abstract action. Check it off with `[x]` once done.
>
> Tests come first and are seen to fail (red) before the implementation that
> makes them pass (green). This feature changes no request/response schema,
> so there is no `contracts/openapi.yaml` regeneration task — the existing
> contract-equality test simply keeps passing.

## Implementation

- [x] T-1. Create and switch to the branch `007-event-deduplication` (constitution Section IV); `git branch --show-current` prints it
- [x] T-2. Unit tests, failing first, in `server/tests/unit/test_services/test_task_deduplication.py`: an event delivered to `complete_task` twice for the same station, with identical category/`occurred_at`/`payload`, is stored only once; two events with the same category and `occurred_at` but different `payload` are both stored; two events with the same category and `payload` but different `occurred_at` are both stored; two different stations delivering the same category/`occurred_at`/`payload` each get their own row (matching spec A-5); a batch that is entirely duplicates still leaves the task `COMPLETED` with `completed_at` set
- [x] T-3. Integration test, failing first, in `server/tests/integration/test_window_request/test_request_flow.py`: place two overlapping window requests for one station; answer both, where one buffered event falls in the overlap and one is unique to each window; the daily report (`GET /agents/{id}/events`) returns exactly three rows, the shared event appearing once; the second delivery's `agent.report` audit row has `new_count` lower than `event_count`, while the first delivery's `new_count` equals its `event_count`
- [x] T-4. In `server/src/warden_server/services/tasks.py`, add a helper that looks up already-stored `Event` rows for the task's `agent_id` whose `occurred_at` is among the incoming batch's timestamps, and change `complete_task` to insert only the events not already present, matched on `(category, occurred_at, payload)`; the task is still marked `COMPLETED` (with `completed_at` set) even when every incoming event turns out to already be known; T-2 passes
- [x] T-5. Add `Index("ix_events_agent_id_occurred_at", "agent_id", "occurred_at")` to `Event.__table_args__` in `server/src/warden_server/models/event.py` (alongside the existing `ix_events_occurred_at`) and a new Alembic revision (down-revision `ee7eb82ccbe5`) with `create_index`/`drop_index`; `alembic upgrade head`, `alembic downgrade -1`, `alembic upgrade head` succeed against a fresh SQLite file
- [x] T-6. In `server/src/warden_server/api/agents.py`, add `new_count` (count of events `complete_task` actually stored) next to the existing `event_count` in the `agent.report` audit entry's `detail`; T-3 passes

## Documentation

- [x] T-7. Update `docs/ru/architecture.md` (canonical): step 4 of "Жизненный цикл обмена агент-сервер" gains a sentence that the server stores only events it does not already have for that station (matched on category, moment, and content), so overlapping window requests do not duplicate the report; remove the now-false "повторные запросы пересекающихся окон сохраняют одно и то же событие дважды" bullet from the Boundaries section
- [x] T-8. Mirror T-7 in `docs/en/architecture.md`, same section and same statements
- [x] T-9. Update `docs/ru/usage.md`: remove the "Повторные запросы пересекающихся окон могут давать в отчёте дубликаты" sentence from the Reports paragraph; extend the honest-status section with the new `ix_events_agent_id_occurred_at` migration's real-PostgreSQL upgrade/downgrade/upgrade check, and note that the deduplication logic itself is proven only by the `pytest` integration test (principle 7 — it needs no live device, unlike a platform collector)
- [x] T-10. Mirror T-9 in `docs/en/usage.md`
- [x] T-11. Update the root `README.md` function-coverage table if its wording for the cross-station/daily report still mentions possible duplicates
- [x] T-12. Amend `.specify/memory/constitution.md` to 1.0.3 (PATCH) through the Section VII procedure: remove the Section V bullet noting that overlapping requests can store the same event twice, add a version-history row explaining this feature closed that boundary, and update the "last amended" date

## Verification

- [x] T-13. Run `ruff check .`, `ruff format --check .`, `mypy src alembic`, and `bandit -c pyproject.toml -r src` in `server/` — all clean
- [x] T-14. Run the full server suite with `pytest --cov=warden_server --cov-report=xml --cov-fail-under=80` and `diff-cover coverage.xml --compare-branch=main --fail-under=80` — green, changed-code coverage at least 80% (113 tests, 98% overall, 100% on changed lines)
- [x] T-15. Against real PostgreSQL run `alembic upgrade head`, `alembic downgrade -1`, `alembic upgrade head` — the new index migration applies and reverses (a throwaway, unmapped-port `postgres:16-alpine` container, not the tracked `docker-compose.yml`, so the user's `gitlab` container on 80/443 was untouched; both `ix_events_occurred_at` and `ix_events_agent_id_occurred_at` confirmed present via `pg_indexes` after the final upgrade; container removed afterward)
- [x] T-16. Repository checks: no `sys.platform`/`platform.system`/platform-specific import was introduced anywhere server-side (principle 1, trivially expected since no agent code changes); a case-insensitive search of the repository (excluding `node_modules`, `.git`, `.venv`) for the project's retired transliterated name finds nothing; `docs/ru` and `docs/en` have matching headings for the pages changed; everything added under `specs/007-event-deduplication/` is English apart from Russian UI/document text quoted verbatim to identify it
- [x] T-17. Set **Status** to `done` in `spec.md`, `plan.md`, and this file
