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
COPY false_sharing_bad.cpp /app/false_sharing_bad.cpp
COPY perf_c2c.txt /app/perf_c2c.txt
RUN g++ -O3 -std=c++17 -pthread /app/false_sharing_bad.cpp -o /app/false_sharing_bad
