# Telemetry collector certificates

The Linux [collector](../implementation/anonymous-product-telemetry-collector.md)
loads its certificate and private key from one systemd credential. The
[rotation command](../../deploy/collector/credentials.py) validates a renewed
pair and replaces that bundle atomically. This prevents a restart from loading
a certificate from one renewal and a key from another.

This is an operator deployment feature. Production collection remains disabled
until the actual endpoint, trust, privacy, resource and platform requirements
in the [V08 contract](../implementation/anonymous-product-telemetry.md) pass.
Preparing credentials does not start a listener or enable client telemetry.

## Prepare the protected bundle

Use a Linux host with systemd, Python 3.12 or later at `/usr/bin/python3`, the
reviewed collector source and an existing Certbot certificate lineage. A free issuer
such as Let's Encrypt is sufficient. This command consumes certificates; it
does not create an account, issue a certificate or configure domain validation.

Replace `telemetry.example.org` in every command with the expected certificate
hostname and use its actual lineage directory. Run the following from the
reviewed source checkout:

```sh
sudo install -d -o root -g root -m 0755 /usr/local/lib/mnemion-telemetry
sudo install -o root -g root -m 0644 deploy/collector/credentials.py \
  /usr/local/lib/mnemion-telemetry/credentials.py
sudo install -d -o root -g root -m 0700 /etc/mnemion-telemetry
sudo /usr/bin/python3 -I \
  /usr/local/lib/mnemion-telemetry/credentials.py \
  --lineage /etc/letsencrypt/live/telemetry.example.org \
  --hostname telemetry.example.org
```

The destination defaults to `/etc/mnemion-telemetry`; `--destination` selects
another absolute, private directory when testing an isolated deployment.
The source certificate and key must be owned by the executing account. With
the root hook, keep the private key root-owned and `0600`; the public
certificate must not be writable by other accounts. Certbot's normal live
symlinks are resolved to owned regular files. Hard-linked, oversized or
concurrently changed input is refused.

Validation uses a bounded TLS handshake entirely in memory. It verifies the
matching key, expected DNS name or IP address, current certificate validity and
at least 24 hours remaining. The supplied certificate is trusted only for that
local check: `validation_scope: "key_pair_hostname_validity"` does not prove
that browsers or released Mnemion clients trust its issuer.

The writer takes a nonwaiting lock, flushes a private temporary file, replaces
`tls.pem` atomically and flushes the directory. The directory remains `0700`
and the bundle `0600`; do not grant the service account access to the original
key. Systemd supplies a private credential snapshot to that account.
The service uses:

```ini
LoadCredential=tls.pem:/etc/mnemion-telemetry/tls.pem
```

Both `--certificate` and `--private-key` in its `ExecStart` refer to
`%d/tls.pem`. Keep the helper and hook root-owned when updating them from a
reviewed release.

## Connect an existing Certbot renewal

Install one deploy hook for this fixed lineage:

```sh
sudo install -d -o root -g root -m 0755 /etc/letsencrypt/renewal-hooks/deploy
sudo tee /etc/letsencrypt/renewal-hooks/deploy/mnemion-telemetry >/dev/null <<'HOOK'
#!/bin/sh
set -eu
exec /usr/bin/python3 -I \
  /usr/local/lib/mnemion-telemetry/credentials.py \
  --lineage /etc/letsencrypt/live/telemetry.example.org \
  --hostname telemetry.example.org \
  --restart-active
HOOK
sudo chown root:root /etc/letsencrypt/renewal-hooks/deploy/mnemion-telemetry
sudo chmod 0755 /etc/letsencrypt/renewal-hooks/deploy/mnemion-telemetry
```

Certbot invokes deploy hooks after a successful renewal. The helper ignores a
`RENEWED_LINEAGE` belonging to another certificate. Use the host's existing
renewal timer or scheduler; installing this hook does not create one. For a
systemd Certbot installation, inspect its existing timer with:

```sh
sudo systemctl status certbot.timer --no-pager
```

With `--restart-active`, a changed bundle triggers a bounded `try-restart` of
`mnemion-telemetry.service` and a subsequent active-state check. An unchanged
bundle is not rewritten and does not restart the collector. Missing, stopped or
failed services are not started. The memory service, its listener and its
certificates are not restarted or replaced by this helper.

A collector restart discards the current open week's in-memory accumulator.
Previously closed reports remain in the aggregate store. This is the
collector's existing retention behavior; rotation never flushes raw reports.

The helper uses the Python standard library, with no OpenSSL executable
dependency. `-I` isolates its Python imports from the caller's environment.

## Migrate an earlier two-file service

First run the preparation command **without** `--restart-active`. Keep the
running service and its existing credentials intact while the new bundle is
validated.

Inspect the effective service, including local overrides:

```sh
sudo systemctl cat mnemion-telemetry.service
sudo systemctl show mnemion-telemetry.service --property=LoadState,ActiveState
```

Update the existing unit or its overrides to use the single `LoadCredential`
line above. Remove the earlier `LoadCredential=fullchain.pem:...` and
`LoadCredential=private-key.pem:...` entries. Change only the two TLS argument
values in `ExecStart` to `%d/tls.pem`; preserve the existing interpreter,
source directory, bind address, port, systemd-socket flag and sandbox settings.
If using a drop-in to replace `LoadCredential` or `ExecStart`, clear that
directive first with an empty assignment before adding its replacement.
Do not replace a custom loopback or IPv6 listener with the template's public
IPv4 example during this migration.

After the effective unit is correct:

```sh
sudo systemctl daemon-reload
sudo systemctl try-restart mnemion-telemetry.service
sudo systemctl show mnemion-telemetry.service --property=ActiveState,SubState,Result
```

Verify that the running endpoint serves the intended certificate through the
deployment's normal TLS check. Keep the earlier protected copies until that
check passes; keep the Certbot lineage for future renewals. This migration
does not enable an intentionally stopped service or alter the socket unit.

## Interpret the result

Successful output is JSON with `schema_version: 1`, `changed`, `activation`
and public certificate fingerprint/expiry metadata. It never prints the
private key. `activation` is `restarted`, `not_running`, `not_requested` or
`unrelated_lineage`. An error exits nonzero and returns a fixed code:

| Code | Recovery |
| --- | --- |
| `invalid_certificate`, `certificate_expiring` | Repair or renew the matching certificate/key for the configured hostname; existing credentials are retained when validation fails. |
| `unsafe_file`, `unsafe_directory`, `file_changed` | Check ownership, permissions, paths and concurrent renewal. Preserve existing files while identifying the cause. |
| `rotation_busy` | Inspect the existing rotation; the command does not queue or retry. |
| `service_state_unavailable`, `service_restart_failed` | The validated bundle has already been installed. Inspect the actual service state before repairing or starting it; repeating an unchanged rotation does not restart it. |
| `credential_operation_failed` | Inspect the private destination and service to establish how far the operation completed before taking another action. |
| `crash_protection_unavailable` | Restore the required Linux process protection before allowing the command to handle keys. |
| `invalid_arguments`, `invalid_configuration`, `invalid_hostname`, `unsupported_platform` | Correct the invocation or run it on the supported Linux host. |

After an activation failure, use an explicit
`systemctl restart mnemion-telemetry.service` only when inspection and any
required repair establish that restarting the existing collector is appropriate.
The renewal helper will not make that recovery decision for a stopped service.

Validation failure does not issue another certificate or fall back to a
different hostname. The helper neither installs public client trust nor
qualifies certificate-chain wire cost, firewall/proxy/provider logging,
monitoring, backups or telemetry anonymity. Those checks remain part of the
[collector deployment requirements](../implementation/anonymous-product-telemetry-collector.md).
