---
name: query-aws-logs
title: Query AWS CloudWatch Logs
type: skill
topics:
  - aws
  - cloudwatch
  - logging
  - debugging
  - cli
summary: >
  Query AWS CloudWatch Logs for application and infrastructure log events using
  filter patterns and Logs Insights, export results to JSON or CSV for debugging
  and analysis, with repeatable local setup for account, region, and default log groups.
references:
  - skills/scaffold-terraform-aws-repo.md
  - articles/aws/aws-cloudwatch-logging-monitoring.md
last-updated: 2026-06-25
---

# Query AWS CloudWatch Logs

Query CloudWatch Logs using filter-pattern searches and Logs Insights queries,
export matched events to JSON or CSV for debugging and analysis. Follow steps
in order.

---

## Prerequisites

- AWS CLI v2 installed (`aws --version`)
- AWS credentials configured via `aws configure`, SSO (`aws sso login`), or environment variables
- IAM permissions: `logs:FilterLogEvents`, `logs:StartQuery`, `logs:GetQueryResults`, `logs:DescribeLogGroups`, `logs:DescribeLogStreams`
- `jq` installed for JSON processing
- Target log group(s) exist in the AWS account

---

## Steps

### Step 1: Configure environment variables

Set default values for account, region, profile, and log group. Source these
from a local `.env` file or export directly. Do not commit this file.

```bash
# Create a local env file (git-ignored) for repeatable setup
cat > .env.cloudwatch-logs <<'ENVEOF'
export AWS_REGION="us-east-1"
export AWS_PROFILE="default"
export CW_LOG_GROUP="/aws/lambda/my-application"
export CW_LIMIT="100"
export CW_OUTPUT_FORMAT="json"
ENVEOF

# Source the env file
source .env.cloudwatch-logs
```

### Step 2: Verify access and list available log groups

```bash
# Verify AWS identity
aws sts get-caller-identity --profile "${AWS_PROFILE}"

# List log groups matching a prefix (adjust prefix as needed)
aws logs describe-log-groups \
  --profile "${AWS_PROFILE}" \
  --region "${AWS_REGION}" \
  --log-group-name-prefix "/aws/" \
  --query 'logGroups[].logGroupName' \
  --output table
```

### Step 3: List log streams in a log group

```bash
# List recent log streams ordered by last event time
aws logs describe-log-streams \
  --profile "${AWS_PROFILE}" \
  --region "${AWS_REGION}" \
  --log-group-name "${CW_LOG_GROUP}" \
  --order-by LastEventTime \
  --descending \
  --limit 20 \
  --query 'logStreams[].{name:logStreamName,lastEvent:lastEventTimestamp}' \
  --output table
```

### Step 4: Query with filter-pattern (simple text search)

Use `filter-log-events` for straightforward text or JSON field matching.
This approach streams results directly without requiring a query ID.

```bash
# Define time window (epoch milliseconds)
START_TIME=$(date -d '1 hour ago' +%s000)
END_TIME=$(date +%s000)

# Filter by text pattern (e.g., ERROR)
aws logs filter-log-events \
  --profile "${AWS_PROFILE}" \
  --region "${AWS_REGION}" \
  --log-group-name "${CW_LOG_GROUP}" \
  --start-time "${START_TIME}" \
  --end-time "${END_TIME}" \
  --filter-pattern "ERROR" \
  --limit "${CW_LIMIT}" \
  --output json > filter-results.json

# Show count and preview
echo "Matched events: $(jq '.events | length' filter-results.json)"
jq -r '.events[] | "\(.timestamp) \(.message)"' filter-results.json | head -20
```

### Step 5: Query with filter-pattern for JSON structured logs

```bash
# Filter by structured JSON field (e.g., level = "ERROR" and statusCode >= 500)
aws logs filter-log-events \
  --profile "${AWS_PROFILE}" \
  --region "${AWS_REGION}" \
  --log-group-name "${CW_LOG_GROUP}" \
  --start-time "${START_TIME}" \
  --end-time "${END_TIME}" \
  --filter-pattern '{ $.level = "ERROR" && $.statusCode >= 500 }' \
  --limit "${CW_LIMIT}" \
  --output json > filter-structured-results.json

echo "Matched events: $(jq '.events | length' filter-structured-results.json)"
```

### Step 6: Query with filter-pattern on specific log streams

```bash
# Query specific log streams within the log group
aws logs filter-log-events \
  --profile "${AWS_PROFILE}" \
  --region "${AWS_REGION}" \
  --log-group-name "${CW_LOG_GROUP}" \
  --log-stream-names "stream-name-1" "stream-name-2" \
  --start-time "${START_TIME}" \
  --end-time "${END_TIME}" \
  --filter-pattern "timeout" \
  --limit "${CW_LIMIT}" \
  --output json > filter-streams-results.json

echo "Matched events: $(jq '.events | length' filter-streams-results.json)"
```

### Step 7: Query with CloudWatch Logs Insights (complex queries)

Use Logs Insights for aggregation, stats, parsing, and multi-field queries.
This is an asynchronous operation: start the query, then poll for results.

```bash
# Define the Logs Insights query
CW_QUERY='fields @timestamp, @message, @logStream
| filter @message like /ERROR/
| sort @timestamp desc
| limit 200'

# Start the query
QUERY_ID=$(aws logs start-query \
  --profile "${AWS_PROFILE}" \
  --region "${AWS_REGION}" \
  --log-group-name "${CW_LOG_GROUP}" \
  --start-time "$(date -d '1 hour ago' +%s)" \
  --end-time "$(date +%s)" \
  --query-string "${CW_QUERY}" \
  --output text --query 'queryId')

echo "Query ID: ${QUERY_ID}"
```

### Step 8: Poll for Logs Insights query results

```bash
# Poll until query completes
STATUS="Running"
while [ "${STATUS}" = "Running" ] || [ "${STATUS}" = "Scheduled" ]; do
  sleep 2
  RESULT=$(aws logs get-query-results \
    --profile "${AWS_PROFILE}" \
    --region "${AWS_REGION}" \
    --query-id "${QUERY_ID}" \
    --output json)
  STATUS=$(echo "${RESULT}" | jq -r '.status')
  echo "Status: ${STATUS}"
done

# Save results
echo "${RESULT}" > insights-results.json

# Show matched record count
MATCHED=$(echo "${RESULT}" | jq -r '.statistics.recordsMatched')
echo "Matched records: ${MATCHED}"

# Preview results
echo "${RESULT}" | jq -r '.results[] | [.[] | .value] | @tsv' | head -20
```

### Step 9: Logs Insights query with aggregation

```bash
# Aggregation query: count errors per log stream over the last 24 hours
CW_AGG_QUERY='fields @logStream
| filter @message like /ERROR/
| stats count(*) as errorCount by @logStream
| sort errorCount desc
| limit 50'

AGG_QUERY_ID=$(aws logs start-query \
  --profile "${AWS_PROFILE}" \
  --region "${AWS_REGION}" \
  --log-group-name "${CW_LOG_GROUP}" \
  --start-time "$(date -d '24 hours ago' +%s)" \
  --end-time "$(date +%s)" \
  --query-string "${CW_AGG_QUERY}" \
  --output text --query 'queryId')

echo "Aggregation Query ID: ${AGG_QUERY_ID}"

# Poll for results
STATUS="Running"
while [ "${STATUS}" = "Running" ] || [ "${STATUS}" = "Scheduled" ]; do
  sleep 2
  AGG_RESULT=$(aws logs get-query-results \
    --profile "${AWS_PROFILE}" \
    --region "${AWS_REGION}" \
    --query-id "${AGG_QUERY_ID}" \
    --output json)
  STATUS=$(echo "${AGG_RESULT}" | jq -r '.status')
done

echo "${AGG_RESULT}" > insights-aggregation-results.json
echo "${AGG_RESULT}" | jq -r '.results[] | [.[] | .value] | @tsv'
```

### Step 10: Export results to JSON

```bash
# Export filter-pattern results to clean JSON (array of events)
jq '[.events[] | {
  timestamp: .timestamp,
  ingestionTime: .ingestionTime,
  logStreamName: .logStreamName,
  message: .message
}]' filter-results.json > export-events.json

echo "Exported $(jq length export-events.json) events to export-events.json"

# Export Logs Insights results to clean JSON
jq '[.results[] | map({(.field): .value}) | add]' \
  insights-results.json > export-insights.json

echo "Exported $(jq length export-insights.json) records to export-insights.json"
```

### Step 11: Export results to CSV

```bash
# Export filter-pattern results to CSV
echo "timestamp,logStreamName,message" > export-events.csv
jq -r '.events[] | [
  .timestamp,
  .logStreamName,
  (.message | gsub(","; ";") | gsub("\n"; " "))
] | @csv' filter-results.json >> export-events.csv

echo "Exported to export-events.csv ($(wc -l < export-events.csv) lines)"

# Export Logs Insights results to CSV
FIELDS=$(jq -r '.results[0] // [] | [.[].field] | join(",")' insights-results.json)
echo "${FIELDS}" > export-insights.csv
jq -r '.results[] | [.[].value] | @csv' \
  insights-results.json >> export-insights.csv

echo "Exported to export-insights.csv ($(wc -l < export-insights.csv) lines)"
```

### Step 12: Clean up local output files

```bash
# List generated files
ls -lh filter-results.json filter-structured-results.json \
  filter-streams-results.json insights-results.json \
  insights-aggregation-results.json export-events.json \
  export-insights.json export-events.csv export-insights.csv \
  2>/dev/null

# Remove all output files when done (optional)
# rm -f filter-*.json insights-*.json export-events.* export-insights.*
```

---

## Examples

### Tail recent Lambda errors

```bash
aws logs filter-log-events \
  --region us-east-1 \
  --log-group-name "/aws/lambda/my-api" \
  --start-time "$(date -d '15 minutes ago' +%s000)" \
  --filter-pattern "ERROR" \
  --limit 50 \
  --output json | jq -r '.events[] | "\(.timestamp) \(.message)"'
```

### Logs Insights: parse and aggregate JSON logs

```bash
aws logs start-query \
  --region us-east-1 \
  --log-group-name "/aws/ecs/my-service" \
  --start-time "$(date -d '6 hours ago' +%s)" \
  --end-time "$(date +%s)" \
  --query-string 'parse @message "* * * *" as ip, user, status, latency
    | filter status >= 500
    | stats avg(latency) as avgLatency, count(*) as cnt by bin(5m)
    | sort cnt desc' \
  --output text --query 'queryId'
```

### Multi-log-group Insights query

```bash
aws logs start-query \
  --region us-east-1 \
  --log-group-names "/aws/lambda/api" "/aws/lambda/worker" \
  --start-time "$(date -d '1 hour ago' +%s)" \
  --end-time "$(date +%s)" \
  --query-string 'fields @timestamp, @message, @logStream
    | filter @message like /timeout|ECONNREFUSED/
    | sort @timestamp desc
    | limit 100' \
  --output text --query 'queryId'
```

---

## Constraints

| Constraint | Rationale |
|---|---|
| Use AWS CloudWatch Logs APIs or `aws` CLI only | No GCP or third-party log tooling; stays within the AWS ecosystem |
| Prefer Logs Insights for complex queries | Filter patterns lack aggregation, parsing, and multi-group support |
| Authentication via standard AWS credential chain or `aws sso login` | Portable across local dev, CI, and SSO-federated accounts |
| No secrets or credentials in committed files | `.env.cloudwatch-logs` is local-only; add to `.gitignore` |
| Epoch timestamps for `--start-time` and `--end-time` | Filter API uses milliseconds, Insights API uses seconds; match each correctly |
| Always set `--limit` on filter queries | Prevents unbounded result sets that exhaust memory or API quota |
| Poll Logs Insights with sleep loop | `start-query` is async; `get-query-results` returns status until `Complete` |
| Export to JSON or CSV only | Keeps outputs portable for downstream tools and spreadsheets |
| Output files not committed to version control | Add `*.csv`, `filter-*.json`, `insights-*.json`, `export-*.json` to `.gitignore` |

---

## Outputs

- `query_id` -- Logs Insights query identifier for retrieving async results
- `output_file` -- path to exported JSON or CSV file with matched log events
- `matched_record_count` -- number of log events matching the filter or query
