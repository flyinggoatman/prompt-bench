# Prompt Bench. Static app plus a small Python server. No build step.
FROM python:3.12-alpine

# Node runs the shared prompt engine behind the agent routes. The page and the
# engine are the same code, lifted out of the page by the build, so serving
# /api/agent means running it rather than writing a second assembler in Python.
RUN apk add --no-cache nodejs

RUN addgroup -S bench && adduser -S -G bench -H -s /sbin/nologin bench

WORKDIR /app
# The wildcards take both benches and both admin pages, and keep working in the
# public build, which ships no offline copy.
COPY --chown=bench:bench prompt-bench*.html /app/
COPY --chown=bench:bench persona-bench.html /app/
COPY --chown=bench:bench admin*.html /app/
COPY --chown=bench:bench server.py README.md /app/
COPY --chown=bench:bench packs /app/packs
COPY --chown=bench:bench uploads /app/uploads
COPY --chown=bench:bench legacy /app/legacy
COPY --chown=bench:bench tools /app/tools
COPY --chown=bench:bench docs /app/docs

USER bench
EXPOSE 8080
ENV BENCH_PORT=8080

# The public health endpoint needs no credentials.
HEALTHCHECK --interval=30s --timeout=3s --retries=3 \
  CMD python3 -c "import urllib.request;urllib.request.urlopen('http://127.0.0.1:8080/healthz',timeout=2)" || exit 1

CMD ["python3", "/app/server.py"]
