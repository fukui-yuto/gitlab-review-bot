FROM python:3.11-slim AS base
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends ca-certificates curl \
    && rm -rf /var/lib/apt/lists/*

# Copy CA cert if present
COPY certs/ /tmp/certs/
RUN if [ -f /tmp/certs/company-ca.pem ]; then \
        cp /tmp/certs/company-ca.pem /usr/local/share/ca-certificates/company-ca.crt && \
        update-ca-certificates; \
    fi && rm -rf /tmp/certs

RUN pip install --no-cache-dir uv

COPY pyproject.toml ./
RUN uv pip install --system --no-cache-dir .

COPY src ./src
COPY config ./config

EXPOSE 8080
CMD ["uvicorn", "review_bot.main:app", "--host", "0.0.0.0", "--port", "8080"]
