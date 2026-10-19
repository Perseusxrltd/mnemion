# Synthetic KeePass interoperability fixtures

These KDBX files were written and reopened independently by **PyKeePass 4.2.0**
on 19 October 2026. They contain invented values only. The password and expected
current fields are intentionally public in `expected.json`; no account exists.
Key files contain the bytes 0 through 31, encoded as KeePass XML v1/v2, raw bytes
and hexadecimal. Never use these passwords or keys for real credentials.

| File | Outer encryption | KDF | Protected fields | Unlock |
| --- | --- | --- | --- | --- |
| `argon2d-aes.kdbx` | AES-256 | Argon2d, 8 MiB / 2 passes / 1 lane | ChaCha20 | Fixture password |
| `argon2id-chacha.kdbx` | ChaCha20 | Argon2id, 8 MiB / 2 passes / 1 lane | ChaCha20 | Fixture password + any supplied key encoding |
| `aes-kdf-salsa.kdbx` | AES-256 | AES-KDF, 1,000 rounds | Salsa20 | Supplied key only |

Each compressed file has two current entries, Unicode groups/values, standard
fields, protected custom properties, empty fields and entry CustomData. One
historical entry, attachment and recycle-bin entry are intentionally omitted by
the transfer. Tests compare all current fields and verify omission counts.
These reduced KDF costs keep tests fast; production exports use Argon2id at
32 MiB, three passes and one lane with fresh salt and encryption material.

PyKeePass is an independent validation tool, not a Mnemion runtime dependency.
Its GPL-licensed code is not included in this repository or the product.
