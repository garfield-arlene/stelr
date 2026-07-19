FROM python:3.12-slim

LABEL maintainer="stelr"
LABEL description="Stelr v5.0.2 — URL bookmark and ranking web app"
LABEL version="5.0.2"
LABEL org.opencontainers.image.title="stelr"
LABEL org.opencontainers.image.version="5.0.2"
LABEL org.opencontainers.image.ref.name="stelr:5.0.2"

ENV DEBIAN_FRONTEND=noninteractive

RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc libpq-dev libxml2-dev libxslt-dev \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app.py .
COPY entrypoint.sh .
COPY plugins/ plugins/
COPY templates/ templates/

RUN mkdir -p /data
RUN chmod +x /app/entrypoint.sh

ENV FLASK_APP=app.py
ENV STORAGE_BACKEND=xml
ENV XML_FILE=/data/links.xml
ENV YAML_FILE=/data/links.yaml
ENV HTML_FILE=/data/links.html
ENV PYTHONPATH=/app
ENV ADMIN_USERNAME=admin
ENV ADMIN_PASSWORD=admin
ENV SESSION_TIMEOUT_MINUTES=30

EXPOSE 5000

ENTRYPOINT ["/app/entrypoint.sh"]
