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
COPY herd_bad.cpp /app/herd_bad.cpp
COPY perf_sched.txt /app/perf_sched.txt
RUN g++ -O3 -std=c++17 -pthread /app/herd_bad.cpp -o /app/herd_bad
