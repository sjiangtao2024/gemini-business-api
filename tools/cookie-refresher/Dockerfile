FROM python:3.11-slim

WORKDIR /app

# Install system dependencies (Chrome + Xvfb) as needed for browser automation.
RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        wget \
        ca-certificates \
        xvfb \
    && rm -rf /var/lib/apt/lists/*

COPY pyproject.toml README.md .
COPY cookie_refresher ./cookie_refresher

RUN pip install --no-cache-dir -e .

ENTRYPOINT ["python", "-m", "cookie_refresher.cli"]
