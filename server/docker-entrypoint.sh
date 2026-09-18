#!/bin/sh
# Applies pending Alembic migrations before starting the server, so a fresh
# database (first `docker compose up`) and an upgraded image (a later one,
# with new migrations already committed) both end up on the right schema
# without a separate manual step.
set -eu

alembic upgrade head
exec "$@"
