#include <algorithm>
#include <cstdint>
#include <cstdlib>
#include <iostream>
#include <vector>

// Deterministic xorshift fill so the serial reference and the candidate sort
// operate on identical data.
static void fill(std::vector<float>& v) {
    std::uint64_t s = 88172645463325252ULL;
    for (auto& x : v) {
        s ^= s << 13; s ^= s >> 7; s ^= s << 17;
        x = static_cast<float>(static_cast<std::int64_t>(s % 2000000) - 1000000) * 0.001f;
    }
}

// Signature: order-sensitive checksum + a sortedness check. Equal signatures
// mean the same multiset in the same (sorted) order.
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
    std::sort(v.begin(), v.end());     // comparison sort, O(n log n) on primitives
    return emit(v) ? 0 : 1;
}
