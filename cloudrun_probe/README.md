# Skirk Cloud Run Probe

Temporary Cloud Run service for measuring whether a real `*.run.app` endpoint works through the restricted network.

Endpoints:

- `/healthz` - returns HTTP 204.
- `/headers` - returns request metadata without auth/cookie headers.
- `/stream` - emits delayed chunks.
- `/ws` - WebSocket echo.

Cleanup is tracked in `cloud_resources/skirk-probe-20260501.json` after deployment.
