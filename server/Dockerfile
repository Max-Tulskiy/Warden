# Runtime image for the Warden server. Migrations run at container start
# (entrypoint.sh), not at build time -- the database is not reachable yet
# during `docker build`, only once compose has started postgres.
FROM python:3.12-slim

WORKDIR /app

# psycopg[binary] ships a self-contained wheel, so no libpq-dev/build-essential
# is needed here -- keeps the image slim and the build fast.
COPY pyproject.toml ./
COPY alembic.ini ./
COPY alembic ./alembic
COPY src ./src

RUN pip install --no-cache-dir . \
    && useradd --create-home --shell /usr/sbin/nologin warden
USER warden

COPY --chown=warden:warden docker-entrypoint.sh /app/docker-entrypoint.sh

EXPOSE 8000

ENTRYPOINT ["/bin/sh", "/app/docker-entrypoint.sh"]
CMD ["uvicorn", "warden_server.main:app", "--host", "0.0.0.0", "--port", "8000"]
