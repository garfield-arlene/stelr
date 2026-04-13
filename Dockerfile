FROM python:3.12-slim

LABEL maintainer="stelr"
LABEL description="Stelr v1.0.0 — URL bookmark and ranking web app"
LABEL version="1.0.0"
LABEL org.opencontainers.image.title="stelr"
LABEL org.opencontainers.image.version="1.0.0"
LABEL org.opencontainers.image.ref.name="stelr:1.0.0"

# System deps for lxml / psycopg2
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc libpq-dev libxml2-dev libxslt-dev \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# Install the stelr package (makes the plugins module resolvable)
RUN pip install --no-cache-dir -e .

# Data volume mount point
RUN mkdir -p /data

ENV FLASK_APP=app.py
ENV STORAGE_BACKEND=xml
ENV XML_FILE=/data/links.xml
ENV YAML_FILE=/data/links.yaml
ENV HTML_FILE=/data/links.html
ENV PYTHONPATH=/app

EXPOSE 5000

CMD ["python", "-m", "gunicorn", "--config", "/app/gunicorn.conf.py", "app:app"]
