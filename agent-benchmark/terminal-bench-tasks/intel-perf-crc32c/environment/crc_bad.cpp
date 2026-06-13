#include <cstdint>
#include <cstdlib>
#include <iostream>
#include <vector>

// Bit-at-a-time software CRC32C (Castagnoli, polynomial 0x1EDC6F41,
// reflected 0x82F63B78). Correct but slow: one byte per inner loop, eight
// shifts per byte, a single serial accumulator.
static std::uint32_t crc32c_sw(const std::uint8_t* p, std::size_t n, std::uint32_t crc) {
    crc = ~crc;
    for (std::size_t i = 0; i < n; ++i) {
        crc ^= p[i];
        for (int k = 0; k < 8; ++k) {
            crc = (crc >> 1) ^ (0x82F63B78u & (-(std::int32_t)(crc & 1)));
        }
    }
    return ~crc;
}

static void fill(std::vector<std::uint8_t>& buf) {
    for (std::size_t i = 0; i < buf.size(); ++i) {
        buf[i] = static_cast<std::uint8_t>(i * 131u + 7u);
    }
}

int main(int argc, char** argv) {
    const std::size_t n = argc > 1 ? std::strtoull(argv[1], nullptr, 10) : 64ULL * 1024 * 1024;
    if (n == 0) { std::cerr << "INVALID_ARGUMENTS\n"; return 2; }
    std::vector<std::uint8_t> buf(n);
    fill(buf);
    const std::uint32_t crc = crc32c_sw(buf.data(), n, 0u);
    std::cout << "VALID crc=" << crc << "\n";
    return 0;
}
