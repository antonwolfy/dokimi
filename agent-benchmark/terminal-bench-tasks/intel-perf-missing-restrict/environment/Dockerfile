FROM ubuntu:22.04

ENV DEBIAN_FRONTEND=noninteractive

RUN apt-get update && apt-get install -y \
    --no-install-recommends \
    build-essential \
    gcc \
    python3 \
    python3-pytest \
    time \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY saxpy_aliasing.c /app/saxpy_aliasing.c
COPY annotate_aliasing.txt /app/annotate_aliasing.txt
RUN gcc -O3 -std=c11 /app/saxpy_aliasing.c -lm -o /app/saxpy_aliasing
