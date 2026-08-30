FROM python:3.12-slim

# Passed in by the container build/publish workflow, read from the
# repo's own VERSION file -- defaults to "dev" for local `docker build`
# so it's never left silently wrong.
ARG VERSION=dev

LABEL maintainer="stelr"
LABEL description="Stelr v${VERSION} — URL bookmark and ranking web app"
LABEL version="${VERSION}"
LABEL org.opencontainers.image.title="stelr"
LABEL org.opencontainers.image.version="${VERSION}"
LABEL org.opencontainers.image.ref.name="stelr:${VERSION}"

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
COPY static/ static/

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
