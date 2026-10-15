FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1
WORKDIR /app

COPY pyproject.toml README.md ./
COPY src ./src
# Editable install: the app finds data/ and runtime/ relative to /app, not site-packages.
RUN pip install -e .

COPY configs ./configs
COPY data ./data
COPY prompts ./prompts

# Non-root user; the app writes only under /app/runtime (mount a volume there to keep state).
RUN useradd --create-home app && mkdir -p /app/runtime && chown -R app /app/runtime
USER app

EXPOSE 8000
HEALTHCHECK CMD python -c "import urllib.request as u; u.urlopen('http://localhost:8000/health')"
CMD ["uvicorn", "capstone.api:app", "--host", "0.0.0.0", "--port", "8000"]
