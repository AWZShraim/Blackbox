# Shared base image for the mediator, the recorder, and the agent-runner.
# Which service a container becomes is decided entirely by docker-compose's
# `command:`/`entrypoint:` — the image is identical. That is deliberate: it
# is what makes it cheap to add an eBPF or MCP-proxy Collector later
# without touching how these services are built (Section 4's Collector
# seam).
FROM python:3.11-slim

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY common/ common/
COPY mediator/ mediator/
COPY recorder/ recorder/
COPY detector/ detector/
COPY scenarios/ scenarios/

ENV PYTHONUNBUFFERED=1
