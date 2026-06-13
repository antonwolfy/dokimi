# Intel perf CRC32C

You are given `/app/crc_bad.cpp`, a CRC32C (Castagnoli) checksum benchmark that
uses a bit-at-a-time software loop with a single serial accumulator. The
included `/app/perf_report.txt` shows `crc32c_sw` dominating runtime.

CRC32C is a known algorithm with a dedicated x86 instruction (`crc32`, SSE4.2).

Create a faster implementation that:

1. Preserves the CLI: optional `<length>` byte count.
2. Produces the **exact same CRC32C value** as the reference for the same input
   (the same `0x82F63B78` reflected polynomial and the same buffer fill).
3. Uses the hardware CRC32C path (`_mm_crc32_u64`/`_mm_crc32_u8`) with
   **runtime CPU dispatch** and a **portable scalar fallback** for hosts
   without SSE4.2.
4. Writes source at `/app/crc_fast.cpp`.
5. Writes an executable binary at `/app/crc_fast`.
6. Prints a line containing `VALID crc=<value>`.

A typical compile command is:

```bash
g++ -O3 -std=c++17 /app/crc_fast.cpp -o /app/crc_fast
```

The verifier checks the CRC against the reference and a known test vector,
requires a large throughput speedup, and checks that the source uses a hardware
CRC intrinsic plus a dispatch/fallback path.
