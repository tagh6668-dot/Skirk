# Go Skirk

Skirk's production client is implemented in Go under `cmd/skirk` and `internal/skirk`.

## Current Modes

- `hybrid-send` and `hybrid-recv`: encrypted file/object round trips over Drive data + Sheets control.
- `e2e`: creates a random payload, sends it through the hybrid transport, receives it back, compares bytes, and optionally cleans up data/control rows.
- `serve-client`: local SOCKS5 listener that sends CONNECT streams through the Drive+Sheets mailbox.
- `serve-exit`: exit poller that reads client stream events, dials target TCP, and writes downstream events back.
- `workspace create/delete`: creates or deletes the temporary Google Sheet used as Skirk's control lane.

## Config

Generate a starter config:

```sh
go run ./cmd/skirk sample-config --out skirk.json --spreadsheet-id SHEET_ID
```

The important fields are:

- `secret`: shared AEAD secret. Use `skirk keygen`.
- `session_id`: optional fixed 32-hex session for a paired client and exit.
- `route.proxy`: restricted-network SOCKS proxy, usually `socks5h://127.0.0.1:1080`.
- `route.google_ip`: known Google edge IP for pinned routing.
- `sheets.spreadsheet_id`: Sheets control-lane spreadsheet.
- `tunnel.chunk_size`: Drive object payload size. Start conservative, then benchmark.
- `tunnel.cleanup_processed`: removes Drive chunks and tombstones processed control rows.

## Why Drive + Sheets

Drive is better for binary chunks than Sheets. Sheets is better as a visible append-only control/index/ACK lane than repeatedly listing Drive folders for discovery. Skirk uses Sheets to announce chunk readiness and Drive to carry encrypted payload blobs.

This improves on a pure Drive queue because data discovery and control state are separated from the binary payload lifecycle. It does not make Google Workspace APIs a low-latency stream substrate; polling and API quotas still define the ceiling.

## Operational Notes

- Use a dedicated Google account or workspace for testing.
- Use a dedicated spreadsheet per Skirk config.
- Keep `chunk_size` within a measured range; larger chunks improve bulk throughput but hurt latency and retries.
- `cleanup_processed` should stay enabled for interactive tests to avoid Drive object buildup.
- The access token can come from `SKIRK_ACCESS_TOKEN`, `auth.access_token`, or `auth.token_command`.

## Validation

Local:

```sh
go test ./...
pytest -q
```

Restricted network substrate:

```sh
go run ./cmd/skirk e2e --config skirk.json --bytes 2048 --delete-after
```

SOCKS path:

Run an exit:

```sh
go run ./cmd/skirk serve-exit --config skirk.json
```

Run a client:

```sh
go run ./cmd/skirk serve-client --config skirk.json --listen 127.0.0.1:18080
```

Then point an app at `socks5h://127.0.0.1:18080`.

## Learning Notes

This follows a split-lane design common in real transports: small ordered control messages are kept separate from heavier data frames. It gives the scheduler room to improve retries, ACKs, adaptive chunking, and cleanup without changing the encrypted data envelope.

## Why This Matters

The hard part is not AES or SOCKS; it is making a brittle, quota-limited substrate fail predictably. The current implementation keeps the core binary envelope independent from Google APIs so future carriers can reuse the same protocol.
