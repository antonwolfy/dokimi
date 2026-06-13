#!/usr/bin/env bash
set -euo pipefail

# Reference solution: a non-comparison radix sort over the float bit pattern.
# Stable ordering is not required, the element type is a fixed-width primitive,
# and the key transform is the standard order-preserving float->uint mapping, so
# a radix pass produces the same sorted multiset far faster than std::sort.
cat > /app/sort_fast.cpp <<'CPP'
#include <cstdint>
#include <cstdlib>
#include <cstring>
#include <iostream>
#include <vector>

static void fill(std::vector<float>& v) {
    std::uint64_t s = 88172645463325252ULL;
    for (auto& x : v) {
        s ^= s << 13; s ^= s >> 7; s ^= s << 17;
        x = static_cast<float>(static_cast<std::int64_t>(s % 2000000) - 1000000) * 0.001f;
    }
}

// Order-preserving float -> uint32 key (flip sign bit for positives, all bits
// for negatives) so an unsigned radix sort yields ascending float order.
static inline std::uint32_t fkey(float f) {
    std::uint32_t u;
    std::memcpy(&u, &f, 4);
    const std::uint32_t sign = u >> 31;
    const std::uint32_t mask = (0u - sign) | 0x80000000u;
    return u ^ mask;
}

static void radix_sort(std::vector<float>& a) {
    const std::size_t n = a.size();
    std::vector<float> b(n);
    for (int shift = 0; shift < 32; shift += 8) {
        std::size_t count[256] = {0};
        for (float f : a) count[(fkey(f) >> shift) & 0xff]++;
        std::size_t sum = 0;
        for (int i = 0; i < 256; ++i) { std::size_t c = count[i]; count[i] = sum; sum += c; }
        for (float f : a) { std::uint8_t k = (fkey(f) >> shift) & 0xff; b[count[k]++] = f; }
        a.swap(b);
    }
}

static bool emit(const std::vector<float>& v) {
    double sig = 0.0;
    for (std::size_t i = 0; i < v.size(); ++i) {
        if (i && v[i] < v[i - 1]) { std::cerr << "NOT_SORTED\n"; return false; }
        sig += static_cast<double>(v[i]) * static_cast<double>((i % 101) + 1);
    }
    std::cout.precision(17);
    std::cout << "VALID sig=" << sig << "\n";
    return true;
}

int main(int argc, char** argv) {
    const std::size_t n = argc > 1 ? std::strtoull(argv[1], nullptr, 10) : 20000000ULL;
    if (n == 0) { std::cerr << "INVALID_ARGUMENTS\n"; return 2; }
    std::vector<float> v(n);
    fill(v);
    radix_sort(v);
    return emit(v) ? 0 : 1;
}
CPP

g++ -O3 -std=c++17 /app/sort_fast.cpp -o /app/sort_fast
