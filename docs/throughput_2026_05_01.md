# Throughput 2026-05-01

Benchmark command:

```sh
./bin/skirk bench \
  --config <direct-config> \
  --temp-workspace \
  --title skirk-bench-direct-20260501153116 \
  --sizes 65536,1048576 \
  --chunk-sizes 65536,262144
```

Route:

```text
direct normal internet
```

Restricted-network throughput was skipped after the normal test showed the current unoptimized Drive+Sheets path is API-call limited. Restricted-network correctness is already proven in `docs/verification_2026_05_01.md`.

## Results

| Payload | Chunk | Chunks | Send | Receive | Cleanup | Send Mbps | Receive Mbps | Round Trip Mbps |
|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| 64 KiB | 64 KiB | 1 | 1.352s | 1.837s | 1.002s | 0.388 | 0.285 | 0.164 |
| 64 KiB | 256 KiB | 1 | 1.034s | 0.911s | 0.911s | 0.507 | 0.575 | 0.269 |
| 1 MiB | 64 KiB | 16 | 15.510s | 11.478s | 14.255s | 0.541 | 0.731 | 0.311 |
| 1 MiB | 256 KiB | 4 | 3.787s | 2.849s | 3.659s | 2.215 | 2.944 | 1.264 |

Best observed case:

```text
1 MiB payload, 256 KiB chunks:
send    2.215 Mbps
receive 2.944 Mbps
round trip 1.264 Mbps
```

The temporary spreadsheet and Drive chunk objects were cleaned up.

## Interpretation

Skirk is currently dominated by Google API call count:

- Each chunk means one Drive upload plus one Sheets append on send.
- Receive does one Sheets read plus Drive downloads.
- Cleanup does Drive deletes plus Sheets tombstones.

Larger chunks are much faster because they amortize the fixed API latency. The 1 MiB / 256 KiB case used 4 chunks and was roughly 4x better than 1 MiB / 64 KiB.

## Next Throughput Work

The fastest path from here is not more tiny tuning; it is reducing API calls and adding concurrency:

- batch Sheets control rows instead of one append per chunk;
- parallel Drive uploads/downloads with a bounded worker pool;
- defer cleanup into a background compactor;
- use 512 KiB to 2 MiB chunks for bulk mode;
- keep smaller chunks only for interactive streams;
- add a scheduler with separate interactive and bulk lanes.

## Learning Notes

This is the classic latency-amortization pattern: object-store APIs are not streams, so throughput improves when each API call carries more useful bytes. That is why a Drive mailbox can look acceptable for bulk transfer but poor for interactive traffic.

## Why This Matters

The benchmark shows Skirk's current ceiling, not the final design ceiling. The protocol works; now the bottleneck is scheduler engineering: batching, parallelism, cleanup policy, and adaptive chunk size.
