FROM ubuntu:22.04

ENV DEBIAN_FRONTEND=noninteractive

RUN apt-get update && apt-get install -y \
    --no-install-recommends \
    python3 \
    python3-pytest \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY perf_stat.txt /app/perf_stat.txt
COPY perf_report.txt /app/perf_report.txt
COPY perf_annotate_accumulate.txt /app/perf_annotate_accumulate.txt
COPY perf_c2c.txt /app/perf_c2c.txt
