FROM python:3.11-slim

WORKDIR /app

# Install system dependencies (Chrome + Xvfb) as needed for browser automation.
RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        wget \
        ca-certificates \
        gnupg \
        xvfb \
    && rm -rf /var/lib/apt/lists/*

# Install Google Chrome
RUN wget -q -O - https://dl-ssl.google.com/linux/linux_signing_key.pub | gpg --dearmor -o /usr/share/keyrings/google-chrome.gpg \
    && echo "deb [arch=amd64 signed-by=/usr/share/keyrings/google-chrome.gpg] http://dl.google.com/linux/chrome/deb/ stable main" > /etc/apt/sources.list.d/google-chrome.list \
    && apt-get update \
    && apt-get install -y --no-install-recommends google-chrome-stable \
    && rm -rf /var/lib/apt/lists/*

COPY pyproject.toml README.md .
COPY cookie_refresher ./cookie_refresher

RUN pip install --no-cache-dir -e .

ENTRYPOINT ["python", "-m", "cookie_refresher.cli"]
