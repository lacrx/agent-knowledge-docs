---
name: query-loki-logs
title: Query Loki Logs
type: skill
topics:
  - loki
  - logql
  - observability
  - troubleshooting
  - grafana
  - aws
summary: >
  Query Loki logs for application and infrastructure troubleshooting using LogQL,
  with configurable endpoint, auth, time windows, label filters, and text search,
  then export results for debugging and analysis.
references:
  - skills/query-aws-logs.md
  - articles/monitoring/loki-query-troubleshooting.md
last-updated: 2026-06-25
---

# Query Loki Logs

Query a Loki instance using LogQL for application and infrastructure log
analysis. Covers endpoint setup, authentication, label-based filtering, full
text search, and result export. Follow steps in order.

---

## Prerequisites

- `curl` installed (used for all Loki HTTP API calls)
- `jq` installed (parses and formats JSON responses)
- Network access to the Loki endpoint (direct or via Grafana Cloud / AWS-hosted Loki)
- Valid credentials for the Loki instance (basic auth, API key, or tenant header)
- Bash shell (all commands assume bash-compatible syntax)

---

## Steps

### Step 1: Set environment variables for endpoint and auth

Store connection details in environment variables. Never commit these values
to files.

```bash
# Loki base URL (no trailing slash)
export LOKI_BASE_URL="https://loki.example.com"

# Tenant ID (required for multi-tenant Loki; use "fake" for single-tenant)
export LOKI_TENANT_ID="my-tenant"

# Basic auth credentials (leave empty if using header-based auth)
export LOKI_USERNAME="loki-reader"
export LOKI_PASSWORD="$(aws secretsmanager get-secret-value \
  --secret-id loki/reader-password \
  --region "${AWS_REGION:-us-east-1}" \
  --query SecretString --output text)"
```

### Step 2: Set default query parameters

Define reusable defaults for service, environment, labels, time range, and
output settings.

```bash
# Target service and environment
export SERVICE_NAME="my-api"
export ENVIRONMENT="prod"
export AWS_REGION="us-east-1"

# Default stream selector labels (comma-separated key=value pairs)
export DEFAULT_LABELS="service=\"${SERVICE_NAME}\",environment=\"${ENVIRONMENT}\""

# Time window (RFC3339 or relative like "1h", "30m", "7d")
export START_TIME="$(date -u -d '1 hour ago' +%Y-%m-%dT%H:%M:%SZ)"
export END_TIME="$(date -u +%Y-%m-%dT%H:%M:%SZ)"

# Result controls
export LIMIT="1000"
export DIRECTION="backward"

# Output settings
export OUTPUT_FORMAT="json"
export OUTPUT_FILE="loki-results.json"
```

### Step 3: Verify Loki connectivity

Confirm the endpoint is reachable and credentials are valid before running
queries.

```bash
curl -s -o /dev/null -w "%{http_code}" \
  -u "${LOKI_USERNAME}:${LOKI_PASSWORD}" \
  -H "X-Scope-OrgID: ${LOKI_TENANT_ID}" \
  "${LOKI_BASE_URL}/ready"
```

Expected output: `200`. If you receive `401` or `403`, check credentials. If
the endpoint uses Grafana Cloud, the base URL typically ends with
`/loki` (e.g., `https://logs-prod-us-central1.grafana.net/loki`).

### Step 4: Query logs by stream labels

Filter logs using stream selector labels. This is the fastest query type
because Loki indexes labels.

```bash
LOGQL_QUERY="{${DEFAULT_LABELS}}"

curl -G -s \
  -u "${LOKI_USERNAME}:${LOKI_PASSWORD}" \
  -H "X-Scope-OrgID: ${LOKI_TENANT_ID}" \
  --data-urlencode "query=${LOGQL_QUERY}" \
  --data-urlencode "start=${START_TIME}" \
  --data-urlencode "end=${END_TIME}" \
  --data-urlencode "limit=${LIMIT}" \
  --data-urlencode "direction=${DIRECTION}" \
  "${LOKI_BASE_URL}/loki/api/v1/query_range" | jq .
```

### Step 5: Query logs with text pattern filter

Combine stream selectors with line filter expressions to search log content
for specific text patterns.

```bash
# Case-insensitive text search within a label-filtered stream
LOGQL_QUERY="{${DEFAULT_LABELS}} |~ \"(?i)error|timeout|exception\""

curl -G -s \
  -u "${LOKI_USERNAME}:${LOKI_PASSWORD}" \
  -H "X-Scope-OrgID: ${LOKI_TENANT_ID}" \
  --data-urlencode "query=${LOGQL_QUERY}" \
  --data-urlencode "start=${START_TIME}" \
  --data-urlencode "end=${END_TIME}" \
  --data-urlencode "limit=${LIMIT}" \
  --data-urlencode "direction=${DIRECTION}" \
  "${LOKI_BASE_URL}/loki/api/v1/query_range" | jq .
```

### Step 6: Query with JSON parsing and field extraction

Parse structured JSON logs and filter on extracted fields.

```bash
# Extract JSON fields and filter by status code
LOGQL_QUERY="{${DEFAULT_LABELS}} | json | status_code >= 500"

curl -G -s \
  -u "${LOKI_USERNAME}:${LOKI_PASSWORD}" \
  -H "X-Scope-OrgID: ${LOKI_TENANT_ID}" \
  --data-urlencode "query=${LOGQL_QUERY}" \
  --data-urlencode "start=${START_TIME}" \
  --data-urlencode "end=${END_TIME}" \
  --data-urlencode "limit=${LIMIT}" \
  --data-urlencode "direction=${DIRECTION}" \
  "${LOKI_BASE_URL}/loki/api/v1/query_range" | jq .
```

### Step 7: Run a custom LogQL query

Use any arbitrary LogQL expression passed via the `LOGQL_QUERY` variable.

```bash
# Set any LogQL query
LOGQL_QUERY='{service="my-api",environment="prod"} |= "request_id=abc-123"'

curl -G -s \
  -u "${LOKI_USERNAME}:${LOKI_PASSWORD}" \
  -H "X-Scope-OrgID: ${LOKI_TENANT_ID}" \
  --data-urlencode "query=${LOGQL_QUERY}" \
  --data-urlencode "start=${START_TIME}" \
  --data-urlencode "end=${END_TIME}" \
  --data-urlencode "limit=${LIMIT}" \
  --data-urlencode "direction=${DIRECTION}" \
  "${LOKI_BASE_URL}/loki/api/v1/query_range" | jq .
```

### Step 8: Export query results to file

Save query output and compute a matched record count.

```bash
LOGQL_QUERY="{${DEFAULT_LABELS}} |~ \"(?i)error\""

curl -G -s \
  -u "${LOKI_USERNAME}:${LOKI_PASSWORD}" \
  -H "X-Scope-OrgID: ${LOKI_TENANT_ID}" \
  --data-urlencode "query=${LOGQL_QUERY}" \
  --data-urlencode "start=${START_TIME}" \
  --data-urlencode "end=${END_TIME}" \
  --data-urlencode "limit=${LIMIT}" \
  --data-urlencode "direction=${DIRECTION}" \
  "${LOKI_BASE_URL}/loki/api/v1/query_range" > "${OUTPUT_FILE}"

# Count matched records
MATCHED=$(jq '[.data.result[].values | length] | add // 0' "${OUTPUT_FILE}")

echo "query_used:    ${LOGQL_QUERY}"
echo "output_file:   ${OUTPUT_FILE}"
echo "matched_record_count: ${MATCHED}"
```

### Step 9: Export results as plain text (optional)

Convert JSON results to a newline-delimited plain-text log file for
downstream consumption or grep-based analysis.

```bash
jq -r '.data.result[] | .stream as $s |
  .values[] | "\(.[0]) [\($s | to_entries | map("\(.key)=\(.value)") | join(","))] \(.[1])"' \
  "${OUTPUT_FILE}" > "loki-results.txt"

echo "Plain text log written to loki-results.txt"
echo "Lines: $(wc -l < loki-results.txt)"
```

### Step 10: Discover available labels and values

Use the Loki labels API to explore what stream labels and values are
available before building queries.

```bash
# List all label names
curl -G -s \
  -u "${LOKI_USERNAME}:${LOKI_PASSWORD}" \
  -H "X-Scope-OrgID: ${LOKI_TENANT_ID}" \
  "${LOKI_BASE_URL}/loki/api/v1/labels" | jq '.data[]'

# List values for a specific label
curl -G -s \
  -u "${LOKI_USERNAME}:${LOKI_PASSWORD}" \
  -H "X-Scope-OrgID: ${LOKI_TENANT_ID}" \
  "${LOKI_BASE_URL}/loki/api/v1/label/service/values" | jq '.data[]'
```

---

## Examples

### Filter by multiple labels

```bash
LOGQL_QUERY='{service="payment-api",environment="prod",region="us-east-1"}'

curl -G -s \
  -u "${LOKI_USERNAME}:${LOKI_PASSWORD}" \
  -H "X-Scope-OrgID: ${LOKI_TENANT_ID}" \
  --data-urlencode "query=${LOGQL_QUERY}" \
  --data-urlencode "start=${START_TIME}" \
  --data-urlencode "end=${END_TIME}" \
  --data-urlencode "limit=500" \
  --data-urlencode "direction=backward" \
  "${LOKI_BASE_URL}/loki/api/v1/query_range" | jq .
```

### Full text search across services

```bash
LOGQL_QUERY='{environment="prod"} |= "OutOfMemoryError"'

curl -G -s \
  -u "${LOKI_USERNAME}:${LOKI_PASSWORD}" \
  -H "X-Scope-OrgID: ${LOKI_TENANT_ID}" \
  --data-urlencode "query=${LOGQL_QUERY}" \
  --data-urlencode "start=$(date -u -d '24 hours ago' +%Y-%m-%dT%H:%M:%SZ)" \
  --data-urlencode "end=$(date -u +%Y-%m-%dT%H:%M:%SZ)" \
  --data-urlencode "limit=200" \
  --data-urlencode "direction=backward" \
  "${LOKI_BASE_URL}/loki/api/v1/query_range" | jq .
```

### AWS-hosted Grafana Loki endpoint

```bash
export LOKI_BASE_URL="https://g-abc123.grafana-workspace.us-east-1.amazonaws.com/loki"
export LOKI_TENANT_ID="fake"
export LOKI_USERNAME="api_key"
export LOKI_PASSWORD="$(aws secretsmanager get-secret-value \
  --secret-id grafana/loki-api-key \
  --region us-east-1 \
  --query SecretString --output text)"

LOGQL_QUERY='{service="order-processor"} | json | latency_ms > 5000'

curl -G -s \
  -u "${LOKI_USERNAME}:${LOKI_PASSWORD}" \
  -H "X-Scope-OrgID: ${LOKI_TENANT_ID}" \
  --data-urlencode "query=${LOGQL_QUERY}" \
  --data-urlencode "start=$(date -u -d '6 hours ago' +%Y-%m-%dT%H:%M:%SZ)" \
  --data-urlencode "end=$(date -u +%Y-%m-%dT%H:%M:%SZ)" \
  --data-urlencode "limit=500" \
  "${LOKI_BASE_URL}/loki/api/v1/query_range" | jq .
```

---

## Constraints

| Constraint | Rationale |
|---|---|
| Use Loki HTTP API and LogQL only | No CloudWatch, GCP logging, or vendor-specific log CLIs |
| No secrets in committed files | Credentials come from env vars or secrets manager at runtime |
| Auth via environment variables only | `LOKI_USERNAME`, `LOKI_PASSWORD`, and `LOKI_TENANT_ID` are never written to disk |
| Always pass `X-Scope-OrgID` header | Required for multi-tenant Loki; harmless for single-tenant |
| Use `query_range` endpoint for time-bounded queries | The `/query` endpoint is for instant queries only |
| URL-encode query parameters with `--data-urlencode` | Prevents shell injection and handles special LogQL characters |
| Default direction is `backward` (newest first) | Matches typical troubleshooting workflow; set `forward` for chronological |
| Limit results with `LIMIT` variable | Prevents unbounded result sets that could overwhelm memory |
| Export both JSON and plain text formats | JSON for programmatic analysis; plain text for grep and human reading |

---

## Outputs

- `query_used` -- the LogQL query string that was executed
- `output_file` -- path to the exported results file (default `loki-results.json`)
- `matched_record_count` -- total number of log lines returned by the query
