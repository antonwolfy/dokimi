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
COPY crc_bad.cpp /app/crc_bad.cpp
COPY perf_report.txt /app/perf_report.txt
RUN g++ -O3 -std=c++17 /app/crc_bad.cpp -o /app/crc_bad
