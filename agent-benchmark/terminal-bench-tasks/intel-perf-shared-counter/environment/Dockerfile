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
COPY shared_counter_bad.cpp /app/shared_counter_bad.cpp
COPY profile_excerpt.txt /app/profile_excerpt.txt
RUN g++ -O3 -std=c++17 -pthread /app/shared_counter_bad.cpp -o /app/shared_counter_bad
