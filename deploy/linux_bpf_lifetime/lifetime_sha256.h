#ifndef LIFETIME_SHA256_H
#define LIFETIME_SHA256_H

#include <stdint.h>
#include <string.h>

/* Compact SHA-256 for the vmlinux BTF digest. No libcrypto dependency. */

static const uint32_t LIFETIME_SHA256_K[64] = {
	0x428a2f98u, 0x71374491u, 0xb5c0fbcfu, 0xe9b5dba5u, 0x3956c25bu, 0x59f111f1u,
	0x923f82a4u, 0xab1c5ed5u, 0xd807aa98u, 0x12835b01u, 0x243185beu, 0x550c7dc3u,
	0x72be5d74u, 0x80deb1feu, 0x9bdc06a7u, 0xc19bf174u, 0xe49b69c1u, 0xefbe4786u,
	0x0fc19dc6u, 0x240ca1ccu, 0x2de92c6fu, 0x4a7484aau, 0x5cb0a9dcu, 0x76f988dau,
	0x983e5152u, 0xa831c66du, 0xb00327c8u, 0xbf597fc7u, 0xc6e00bf3u, 0xd5a79147u,
	0x06ca6351u, 0x14292967u, 0x27b70a85u, 0x2e1b2138u, 0x4d2c6dfcu, 0x53380d13u,
	0x650a7354u, 0x766a0abbu, 0x81c2c92eu, 0x92722c85u, 0xa2bfe8a1u, 0xa81a664bu,
	0xc24b8b70u, 0xc76c51a3u, 0xd192e819u, 0xd6990624u, 0xf40e3585u, 0x106aa070u,
	0x19a4c116u, 0x1e376c08u, 0x2748774cu, 0x34b0bcb5u, 0x391c0cb3u, 0x4ed8aa4au,
	0x5b9cca4fu, 0x682e6ff3u, 0x748f82eeu, 0x78a5636fu, 0x84c87814u, 0x8cc70208u,
	0x90befffau, 0xa4506cebu, 0xbef9a3f7u, 0xc67178f2u
};

static inline uint32_t lifetime_rotr(uint32_t x, uint32_t n)
{
	return (x >> n) | (x << (32u - n));
}

static inline void lifetime_sha256_block(uint32_t h[8], const uint8_t block[64])
{
	uint32_t w[64];
	uint32_t a, b, c, d, e, f, g, hh;
	int i;

	for (i = 0; i < 16; i++) {
		w[i] = ((uint32_t)block[i * 4] << 24) | ((uint32_t)block[i * 4 + 1] << 16) |
			((uint32_t)block[i * 4 + 2] << 8) | (uint32_t)block[i * 4 + 3];
	}
	for (i = 16; i < 64; i++) {
		uint32_t s0 = lifetime_rotr(w[i - 15], 7) ^ lifetime_rotr(w[i - 15], 18) ^ (w[i - 15] >> 3);
		uint32_t s1 = lifetime_rotr(w[i - 2], 17) ^ lifetime_rotr(w[i - 2], 19) ^ (w[i - 2] >> 10);
		w[i] = w[i - 16] + s0 + w[i - 7] + s1;
	}
	a = h[0];
	b = h[1];
	c = h[2];
	d = h[3];
	e = h[4];
	f = h[5];
	g = h[6];
	hh = h[7];
	for (i = 0; i < 64; i++) {
		uint32_t S1 = lifetime_rotr(e, 6) ^ lifetime_rotr(e, 11) ^ lifetime_rotr(e, 25);
		uint32_t ch = (e & f) ^ ((~e) & g);
		uint32_t t1 = hh + S1 + ch + LIFETIME_SHA256_K[i] + w[i];
		uint32_t S0 = lifetime_rotr(a, 2) ^ lifetime_rotr(a, 13) ^ lifetime_rotr(a, 22);
		uint32_t maj = (a & b) ^ (a & c) ^ (b & c);
		uint32_t t2 = S0 + maj;
		hh = g;
		g = f;
		f = e;
		e = d + t1;
		d = c;
		c = b;
		b = a;
		a = t1 + t2;
	}
	h[0] += a;
	h[1] += b;
	h[2] += c;
	h[3] += d;
	h[4] += e;
	h[5] += f;
	h[6] += g;
	h[7] += hh;
}

static inline void lifetime_sha256(const uint8_t *msg, uint64_t len, uint8_t out[32])
{
	uint32_t h[8] = {
		0x6a09e667u, 0xbb67ae85u, 0x3c6ef372u, 0xa54ff53au,
		0x510e527fu, 0x9b05688cu, 0x1f83d9abu, 0x5be0cd19u
	};
	uint8_t block[64];
	uint64_t off = 0;
	uint64_t bits = len * 8u;

	while (len - off >= 64u) {
		lifetime_sha256_block(h, msg + off);
		off += 64u;
	}
	memset(block, 0, sizeof block);
	if (len > off)
		memcpy(block, msg + off, (size_t)(len - off));
	block[len - off] = 0x80u;
	if (len - off >= 56u) {
		lifetime_sha256_block(h, block);
		memset(block, 0, sizeof block);
	}
	block[56] = (uint8_t)(bits >> 56);
	block[57] = (uint8_t)(bits >> 48);
	block[58] = (uint8_t)(bits >> 40);
	block[59] = (uint8_t)(bits >> 32);
	block[60] = (uint8_t)(bits >> 24);
	block[61] = (uint8_t)(bits >> 16);
	block[62] = (uint8_t)(bits >> 8);
	block[63] = (uint8_t)bits;
	lifetime_sha256_block(h, block);
	for (int i = 0; i < 8; i++) {
		out[i * 4] = (uint8_t)(h[i] >> 24);
		out[i * 4 + 1] = (uint8_t)(h[i] >> 16);
		out[i * 4 + 2] = (uint8_t)(h[i] >> 8);
		out[i * 4 + 3] = (uint8_t)h[i];
	}
}

static inline int lifetime_sha256_selftest(void)
{
	static const uint8_t abc_expect[32] = {
		0xba, 0x78, 0x16, 0xbf, 0x8f, 0x01, 0xcf, 0xea, 0x41, 0x41, 0x40, 0xde, 0x5d, 0xae, 0x22, 0x23,
		0xb0, 0x03, 0x61, 0xa3, 0x96, 0x17, 0x7a, 0x9c, 0xb4, 0x10, 0xff, 0x61, 0xf2, 0x00, 0x15, 0xad
	};
	static const uint8_t empty_expect[32] = {
		0xe3, 0xb0, 0xc4, 0x42, 0x98, 0xfc, 0x1c, 0x14, 0x9a, 0xfb, 0xf4, 0xc8, 0x99, 0x6f, 0xb9, 0x24,
		0x27, 0xae, 0x41, 0xe4, 0x64, 0x9b, 0x93, 0x4c, 0xa4, 0x95, 0x99, 0x1b, 0x78, 0x52, 0xb8, 0x55
	};
	uint8_t out[32];

	lifetime_sha256((const uint8_t *)"abc", 3, out);
	if (memcmp(out, abc_expect, 32) != 0)
		return -1;
	lifetime_sha256((const uint8_t *)"", 0, out);
	if (memcmp(out, empty_expect, 32) != 0)
		return -1;
	return 0;
}

#endif
