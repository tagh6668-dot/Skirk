# Skirk Modes

Date: 2026-05-01

Skirk now has a shared encrypted BlobQ core and selectable transports.

## Implemented Selectable Transports

### `local`

Deterministic filesystem backend for E2E tests.

```bash
python3 -m skirk e2e-local
```

### `gcs`

Cloud Storage encrypted object queue.

Best for high-throughput bulk transfer when latency is not important.

```bash
SECRET="$(python3 -m skirk keygen)"
python3 -m skirk blobq-send \
  --transport gcs \
  --bucket YOUR_BUCKET \
  --secret "$SECRET" \
  ./input.bin

python3 -m skirk blobq-recv \
  --transport gcs \
  --bucket YOUR_BUCKET \
  --secret "$SECRET" \
  --session SESSION_FROM_SEND \
  ./output.bin
```

Routing options:

```bash
--route-mode real-pinned
--route-mode google-front-pinned
--proxy socks5h://127.0.0.1:1080
--google-ip 216.239.38.120
```

### `drive`

Drive encrypted file queue.

Best as a fallback when Cloud Storage writes fail but Drive API works. It uses Drive files as chunks and can optionally place them in a configured folder.

```bash
python3 -m skirk blobq-send \
  --transport drive \
  --drive-folder-id YOUR_FOLDER_ID \
  --secret "$SECRET" \
  ./input.bin
```

### `sheets`

Sheets append-only encrypted row log.

Best as a tiny control channel or low-rate mailbox. Use a small chunk size because Sheets cells are not a binary object store.

```bash
python3 -m skirk blobq-send \
  --transport sheets \
  --spreadsheet-id YOUR_SHEET_ID \
  --sheet-range 'skirk!A:D' \
  --chunk-size 32768 \
  --secret "$SECRET" \
  ./small-input.bin
```

## Template / Probe Modes

### `apps-script-goose2`

Template:

`skirk/templates/apps_script/Code.gs`

This is the interactive TCP candidate: client sends encrypted frames to Apps Script, Apps Script forwards ciphertext to an owned exit. It is not a general object queue, and it needs an exit service before live E2E.

### `app-engine-stream`

Template:

`skirk/templates/app_engine`

This is the next streaming candidate to test if you approve App Engine creation. Creating App Engine permanently selects the project's App Engine region, so the probe did not create it automatically.

### `cloudrun-stream`

Probe:

`cloud_resources/skirk-probe-20260501-results.md`

This failed in the tested restricted network. The service works on normal internet, but `run.app` is not reachable through the SOCKS path and Google-SNI mismatch does not route to the service.

## Operational Notes

- BlobQ is encrypted end-to-end at the object/chunk layer.
- Object names expose session id, direction, and sequence, but not plaintext payload.
- Cloud Storage is the best high-throughput bulk substrate.
- Drive and Sheets are slower fallbacks.
- Apps Script is the likely interactive fallback but must be quota-governed.
- None of these modes should be operated as an unauthenticated public proxy.

## Verification

Run:

```bash
pytest -q
python3 -m skirk e2e-local
python3 -m skirk modes
```
