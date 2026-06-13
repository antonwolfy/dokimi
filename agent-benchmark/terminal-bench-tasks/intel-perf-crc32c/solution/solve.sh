#!/usr/bin/env bash
set -euo pipefail

cat > /app/crc_fast.cpp <<'CPP'
#include <cstdint>
#include <cstdlib>
#include <cstring>
#include <iostream>
#include <vector>

#if defined(__x86_64__) || defined(__i386__)
#include <nmmintrin.h>
#include <cpuid.h>
static bool has_sse42() {
    unsigned eax, ebx, ecx, edx;
    if (!__get_cpuid(1, &eax, &ebx, &ecx, &edx)) return false;
    return (ecx & bit_SSE4_2) != 0;
}
#else
static bool has_sse42() { return false; }
#endif

// Portable scalar fallback (matches the slow reference bit-for-bit).
static std::uint32_t crc32c_sw(const std::uint8_t* p, std::size_t n, std::uint32_t crc) {
    crc = ~crc;
    for (std::size_t i = 0; i < n; ++i) {
        crc ^= p[i];
        for (int k = 0; k < 8; ++k)
            crc = (crc >> 1) ^ (0x82F63B78u & (-(std::int32_t)(crc & 1)));
    }
    return ~crc;
}

#if defined(__x86_64__) || defined(__i386__)
__attribute__((target("sse4.2")))
static std::uint32_t crc32c_hw(const std::uint8_t* p, std::size_t n) {
    std::uint64_t c = 0xFFFFFFFFu;
    std::size_t i = 0;
    for (; i + 8 <= n; i += 8) {
        std::uint64_t v;
        std::memcpy(&v, p + i, 8);
        c = _mm_crc32_u64(c, v);
    }
    std::uint32_t c32 = static_cast<std::uint32_t>(c);
    for (; i < n; ++i) c32 = _mm_crc32_u8(c32, p[i]);
    return c32 ^ 0xFFFFFFFFu;
}
#endif

static void fill(std::vector<std::uint8_t>& buf) {
    for (std::size_t i = 0; i < buf.size(); ++i)
        buf[i] = static_cast<std::uint8_t>(i * 131u + 7u);
}

int main(int argc, char** argv) {
    const std::size_t n = argc > 1 ? std::strtoull(argv[1], nullptr, 10) : 64ULL * 1024 * 1024;
    if (n == 0) { std::cerr << "INVALID_ARGUMENTS\n"; return 2; }
    std::vector<std::uint8_t> buf(n);
    fill(buf);
    std::uint32_t crc;
#if defined(__x86_64__) || defined(__i386__)
    crc = has_sse42() ? crc32c_hw(buf.data(), n) : crc32c_sw(buf.data(), n, 0u);
#else
    crc = crc32c_sw(buf.data(), n, 0u);
#endif
    std::cout << "VALID crc=" << crc << "\n";
    return 0;
}
CPP

g++ -O3 -std=c++17 /app/crc_fast.cpp -o /app/crc_fast
