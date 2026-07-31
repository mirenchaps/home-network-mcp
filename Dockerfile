# home-network-mcp/Dockerfile
#
# Builds the Prometheus metrics exporter into a Docker image.
# Only exporter.py and its dependencies are needed at runtime —
# server.py (the MCP server) is a separate process run outside Docker.
#
# Build:  docker build -t home-network-mcp .
# Run:    docker run -p 8000:8000 \
#           -e GRAFANA_REMOTE_WRITE_URL=... \
#           -e GRAFANA_USER_ID=... \
#           -e GRAFANA_API_KEY=... \
#           home-network-mcp
#
# Docs: https://docs.docker.com/reference/dockerfile/

# --- build stage: install dependencies into a clean layer ---
FROM python:3.12-slim AS builder

WORKDIR /app

# Copy only the requirements file first so Docker can cache this layer.
# If requirements.txt hasn't changed, this layer is reused on every build.
COPY requirements.txt .
RUN pip install --no-cache-dir --prefix=/install -r requirements.txt

# --- runtime stage: copy installed packages + app code ---
FROM python:3.12-slim

WORKDIR /app

# Copy the installed packages from the builder stage
COPY --from=builder /install /usr/local

# Copy application source
COPY exporter.py runner.py ./
COPY scripts/ ./scripts/

# The exporter serves metrics on port 8000
EXPOSE 8000

# Credentials are injected at runtime via environment variables — never baked in.
# See alloy-config.river for the variable names Grafana Alloy expects.
ENV GRAFANA_REMOTE_WRITE_URL=""
ENV GRAFANA_USER_ID=""
ENV GRAFANA_API_KEY=""

CMD ["python", "exporter.py"]
