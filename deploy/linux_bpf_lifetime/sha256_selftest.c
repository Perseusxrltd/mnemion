#include "lifetime_sha256.h"

int main(void)
{
	return lifetime_sha256_selftest() == 0 ? 0 : 1;
}
