# Prompt Bench. Static app plus a small Python server. No build step, no dependencies.
FROM python:3.12-alpine

RUN addgroup -S bench && adduser -S -G bench -H -s /sbin/nologin bench

WORKDIR /app
COPY --chown=bench:bench prompt-bench.html admin.html server.py README.md /app/
COPY --chown=bench:bench prompt-bench-offline.html /app/
COPY --chown=bench:bench packs /app/packs
COPY --chown=bench:bench uploads /app/uploads
COPY --chown=bench:bench legacy /app/legacy

USER bench
EXPOSE 8080
ENV BENCH_PORT=8080

# The public health endpoint needs no credentials.
HEALTHCHECK --interval=30s --timeout=3s --retries=3 \
  CMD python3 -c "import urllib.request;urllib.request.urlopen('http://127.0.0.1:8080/healthz',timeout=2)" || exit 1

CMD ["python3", "/app/server.py"]
