# Verification 2026-05-01

## Local Tests

```text
go test ./...    PASS
pytest -q        PASS
```

Coverage includes:

- AEAD envelope seal/open and tamper rejection.
- Hybrid Drive+Sheets send/receive over in-memory stores.
- SOCKS5 dialer interoperability.
- Local SOCKS client to Skirk exit over mailbox stores.
- Existing Python prototype tests.

## Restricted Proxy E2E

Route:

```text
socks5h://127.0.0.1:1080
```

Command shape:

```sh
go run ./cmd/skirk e2e --config <temp-config> --bytes 2048 --delete-after
```

Result:

```json
{
  "result": "pass",
  "bytes": 2048,
  "chunk_size": 8192,
  "send_chunks": 1,
  "receive_chunks": 1,
  "duration_ms": 252480
}
```

The temporary spreadsheet was deleted after the run.

Interpretation: Drive and Sheets remain reachable through the restricted SOCKS path, and the Go implementation completes an encrypted byte-for-byte round trip. The runtime is dominated by the slow proxy path.

## Normal Internet Baseline

Command shape:

```sh
go run ./cmd/skirk e2e --config <direct-config> --bytes 8192 --delete-after
```

Result:

```json
{
  "result": "pass",
  "bytes": 8192,
  "chunk_size": 8192,
  "send_chunks": 2,
  "receive_chunks": 2,
  "duration_ms": 4941
}
```

The temporary spreadsheet was deleted after the run.

## Learning Notes

The same config working through the restricted proxy is the key predicate. Once that predicate is true, normal-internet benchmarks are useful for estimating the transport's own overhead without confusing it with the current slow access path.

## Why This Matters

Drive+Sheets can be made reliable, but not magically low-latency. The production work should now focus on adaptive chunk sizing, request timing metrics, and carrier selection so Skirk can choose the best available mode instead of assuming one universal substrate.
