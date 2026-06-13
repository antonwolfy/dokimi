FROM ubuntu:22.04

ENV DEBIAN_FRONTEND=noninteractive

RUN apt-get update && apt-get install -y \
    --no-install-recommends \
    build-essential \
    g++ \
    python3 \
    python3-pytest \
    time \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY rwlock_bad.cpp /app/rwlock_bad.cpp
COPY perf_report.txt /app/perf_report.txt
RUN g++ -O3 -std=c++17 -pthread /app/rwlock_bad.cpp -o /app/rwlock_bad
