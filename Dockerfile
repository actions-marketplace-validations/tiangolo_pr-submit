FROM python:3.14-slim

COPY --from=ghcr.io/astral-sh/uv:0.9.11 /uv /uvx /bin/

ENV UV_NO_DEV=1 \
    UV_PYTHON_DOWNLOADS=0

WORKDIR /app

COPY pyproject.toml uv.lock /app/
RUN uv sync --locked

COPY pr_submit /app/pr_submit

ENV PATH="/app/.venv/bin:$PATH" \
    PYTHONPATH="/app"

CMD ["python", "-m", "pr_submit.action"]
