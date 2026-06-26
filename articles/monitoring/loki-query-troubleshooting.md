---
title: Loki Query Troubleshooting
topics:
  - aws
  - loki
  - logging
  - observability
  - debugging
skills:
  - query-loki-logs
summary: >
  Troubleshooting guide for Loki log queries in AWS environments — covering LogQL patterns, common failure modes, and when to choose Loki over CloudWatch Logs.
aliases:
  - loki logql debugging
  - grafana loki aws logs
  - logql query errors
related:
  - aws-cloudwatch-logging-monitoring
last-updated: 2026-06-25
---

# Loki Query Troubleshooting

## Overview

Loki is a log aggregation system designed for cost-effective, label-indexed log storage. Unlike CloudWatch Logs, which indexes the full text of every log line, Loki only indexes a small set of labels and stores log content in compressed chunks. This architectural difference makes Loki cheaper at scale but also means that query failures tend to be label-related or time-window-related rather than permission-related.

When running Loki alongside AWS workloads — whether self-hosted on ECS/EKS, via Grafana Cloud, or through a managed Loki-compatible endpoint — the most frequent troubleshooting problems fall into a small number of categories: missing or misnamed labels, bad LogQL syntax, time range mismatches, high-cardinality label explosions, delayed ingestion, and authentication or tenant isolation issues.

This article covers how to diagnose each of these, explains useful LogQL patterns, and provides guidance on when Loki is the right choice versus CloudWatch Logs. For executable query procedures, use the companion skill.

> **Skill:** For step-by-step log querying procedures, use the `query-loki-logs` skill.

---

## Loki vs. CloudWatch Logs

Understanding the differences between Loki and CloudWatch Logs helps you choose the right tool and avoid applying CloudWatch mental models to Loki queries.

| Dimension | CloudWatch Logs | Loki |
|---|---|---|
| Indexing | Full-text indexing on all log content | Label-only indexing; log content is not indexed |
| Query language | CloudWatch Insights (SQL-like) | LogQL (PromQL-inspired, stream selectors + pipeline) |
| Cost driver | Ingestion volume + storage + queries scanned | Storage + query time window (not content scanned) |
| Label model | Log group + log stream (fixed hierarchy) | Arbitrary key-value labels (flexible, user-defined) |
| Retention | Per log group, configurable | Per tenant, configured at Loki server level |
| AWS integration | Native (IAM, Lambda, ECS built-in) | Requires a log shipper (Promtail, Grafana Agent, Fluent Bit) |
| Best for | Low-volume, tightly AWS-coupled workloads | High-volume, multi-cloud, cost-sensitive logging |

**When to use CloudWatch Logs:** You need zero-setup logging for Lambda, ECS, or other AWS services. You want native IAM-based access control. Your log volume is modest and you value deep AWS console integration over query flexibility.

**When to use Loki:** You have high log volume and need to control costs. You already use Grafana for dashboards. You want a unified logging layer across AWS, on-prem, or multi-cloud. You need flexible label-based routing and multi-tenant isolation.

Many teams run both — CloudWatch for AWS-native service logs and operational alerts, Loki for application-level logs with richer querying and longer retention.

---

## LogQL Fundamentals

LogQL queries have two parts: a **stream selector** (which labels to match) and an optional **pipeline** (filters, parsers, formatters applied to each log line).

### Stream Selectors

Stream selectors are mandatory and use label matchers inside curly braces:

```logql
{namespace="production", app="api-gateway"}
```

Supported operators: `=` (exact), `!=` (not equal), `=~` (regex match), `!~` (regex exclude).

A query with no stream selector or an empty `{}` selector scans every stream in the tenant — Loki will reject this on most configurations because it would be catastrophically expensive.

### Pipeline Stages

Pipeline stages chain after the stream selector with `|`:

```logql
{app="order-service"} |= "timeout" | json | duration > 5s
```

Common pipeline stages:

| Stage | Purpose | Example |
|---|---|---|
| `\|= "text"` | Line contains text | `\|= "ERROR"` |
| `\|~ "regex"` | Line matches regex | `\|~ "status=[45]\\d{2}"` |
| `!= "text"` | Line does not contain text | `!= "healthcheck"` |
| `json` | Parse line as JSON, extract labels | `\| json` |
| `logfmt` | Parse key=value format | `\| logfmt` |
| `pattern` | Extract fields with pattern syntax | `\| pattern "<ip> - <_> <method>"` |
| `line_format` | Reformat the output line | `\| line_format "{{.method}} {{.status}}"` |
| `label_format` | Rename or transform labels | `\| label_format svc=app` |
| `unwrap` | Extract numeric value for aggregation | `\| unwrap duration` |

### Aggregation Queries (Metric Queries)

LogQL can produce numeric results for dashboards and alerting:

```logql
# Count error lines per minute by service
sum by (app) (rate({namespace="production"} |= "ERROR" [1m]))

# 95th percentile response time from JSON logs
quantile_over_time(0.95, {app="api"} | json | unwrap response_time_ms [5m])
```

These metric queries are essential for Loki-based alerting rules in Grafana, but they are also where performance problems most often appear — a poorly scoped stream selector combined with a wide time range and an `unwrap` operation can time out.

---

## Common Failure Modes

### Missing or Misnamed Labels

**Symptom:** Query returns no results despite logs being ingested.

Loki does not index log content — if your stream selector references a label that does not exist, you get zero results with no error. This is the single most common Loki debugging issue.

**How to diagnose:**

1. Check available labels: query the `/loki/api/v1/labels` endpoint or use the Grafana Explore label browser.
2. Check label values: query `/loki/api/v1/label/{name}/values` to see what values exist.
3. Compare your label names against the Promtail/Grafana Agent configuration. AWS-specific labels like `__aws_ecs_cluster` may be renamed or dropped during relabeling.

**Common AWS-specific gotchas:**

- ECS tasks using the Fluent Bit Loki output plugin: labels come from the plugin configuration, not automatically from ECS metadata. You must explicitly map container name, task definition, and cluster to Loki labels.
- Fargate tasks: container metadata is available via the ECS metadata endpoint, but your log shipper must be configured to extract it. Labels like `container_name` or `task_id` are not automatic.
- EC2-based workloads using Promtail: the EC2 service discovery config must include the right `relabel_configs` to map instance tags to Loki labels.

### Bad LogQL Syntax

**Symptom:** Parse errors or unexpected results.

Common syntax mistakes:

| Mistake | Wrong | Correct |
|---|---|---|
| Missing braces in selector | `app="foo" \|= "error"` | `{app="foo"} \|= "error"` |
| Wrong filter operator | `{app="foo"} \| "error"` | `{app="foo"} \|= "error"` |
| Regex without escaping | `{app=~"svc-.*"}` using `.` to mean literal dot | `{app=~"svc-\\..*"}` |
| Unwrap on non-numeric field | `\| json \| unwrap user_id` | `\| json \| unwrap response_ms` (must be numeric) |
| Rate without range vector | `rate({app="foo"} \|= "err")` | `rate({app="foo"} \|= "err" [5m])` |

### Wrong Time Windows

**Symptom:** Query returns results for the wrong period, or returns nothing when logs exist.

Loki stores timestamps at nanosecond precision but query time ranges are typically specified at the minute or hour level. Mismatches happen because:

- **Timezone confusion:** Grafana sends queries in UTC by default. If your logs are timestamped in local time and you are filtering by parsed timestamp, the offset can hide results.
- **Too-narrow window:** Querying a 5-minute window when the log shipper has a 2-minute flush interval means you may miss logs at the boundary.
- **Too-wide window:** Querying a 30-day range on a metric query will almost certainly time out. Loki is designed for queries spanning hours to days, not weeks.

**Rule of thumb:** Start with a 1-hour window and narrow from there. For metric queries with `rate()` or `sum()`, keep the outer range under 24 hours unless you have specifically tuned Loki's query limits.

### High-Cardinality Labels

**Symptom:** Slow ingestion, `too many streams` errors, or degraded query performance.

Loki creates a separate stream for each unique label combination. Labels with high cardinality — such as request ID, user ID, trace ID, or IP address — create millions of streams and will degrade or crash the ingester.

**What belongs as a label:**

- Service name, namespace, environment, cluster, region, log level — low cardinality, stable values.

**What does NOT belong as a label:**

- Request ID, user ID, session ID, IP address, timestamp components — use `| json` or `| logfmt` to extract these at query time instead.

If you have already ingested high-cardinality labels, you will need to update the log shipper config to drop them and wait for the old streams to age out of retention.

### Delayed Ingestion

**Symptom:** Logs appear in Loki several minutes after they were generated, or recent logs are missing.

Possible causes:

- **Log shipper buffering:** Promtail and Fluent Bit buffer logs before sending. Default flush intervals are typically 1-5 seconds, but backpressure from a slow Loki endpoint can increase this.
- **Out-of-order timestamps:** Loki rejects log entries with timestamps older than the most recent entry for the same stream (unless `unordered_writes` is enabled). This is common when multiple containers write to the same stream with slightly skewed clocks.
- **Network latency to Loki endpoint:** If Loki is in a different region than your workloads, or if you are pushing to Grafana Cloud from a VPC without a direct connect path, network latency adds delay.

**Diagnosis:** Check the log shipper metrics (Promtail exposes `/metrics` with counters for dropped and delayed entries). Check Loki's distributor metrics for `loki_distributor_lines_received_total` vs `loki_distributor_bytes_received_total`.

### Authentication and Tenant Issues

**Symptom:** 401/403 errors, or queries return empty results despite logs being ingested.

- **Multi-tenant Loki:** Each tenant's logs are isolated. If your query uses the wrong `X-Scope-OrgID` header, you will see zero results — not an error. Verify the tenant ID in both the log shipper config and your query client.
- **Grafana Cloud:** Authentication uses an API key or service account token. Expired or rotated tokens produce 401 errors. Check the `Authorization` header in your datasource configuration.
- **AWS-hosted Loki behind ALB:** If your ALB terminates TLS and forwards to Loki over HTTP, ensure the health check path is `/ready` (not `/`). Misconfigured health checks cause the target group to drain Loki instances.

---

## Useful LogQL Patterns for AWS Workloads

### Filtering ECS Task Logs by Container

```logql
{cluster="prod", service="api"} |= "container_name" | json | container_name="web"
```

If `container_name` is a label (preferred), use it directly in the stream selector instead of parsing it from the log line.

### Extracting Structured Fields from JSON Logs

```logql
{app="order-service"} | json | status >= 500 | line_format "{{.timestamp}} {{.method}} {{.path}} {{.status}} {{.duration_ms}}ms"
```

This parses each line as JSON, filters to 5xx responses, and reformats the output for readability.

### Counting Errors by Service Over Time

```logql
sum by (app) (rate({namespace="production"} |= "level=error" [5m]))
```

Use this as a Grafana alerting rule to detect error rate spikes.

### Finding Slow Requests

```logql
{app="api-gateway"} | json | response_time_ms > 2000 | line_format "{{.timestamp}} {{.path}} took {{.response_time_ms}}ms"
```

### Correlating with Request IDs

```logql
{namespace="production"} |= "req-abc123-def456"
```

Since request IDs should never be labels (high cardinality), use text search (`|=`) to find all log lines across services containing a specific request ID. This is the Loki equivalent of a CloudWatch Insights `filter @message like /req-abc123/` query.

---

## Exporting Logs for Local Analysis

Loki is designed for interactive queries, not bulk export. When you need to export logs for local analysis or incident review, use these approaches:

**LogCLI (Loki's CLI tool):**

```bash
logcli query '{app="api"}' --from="2026-06-25T00:00:00Z" --to="2026-06-25T01:00:00Z" \
  --limit=10000 --output=jsonl > incident-logs.jsonl
```

**Grafana Explore:** Use the "Download" button in Explore to export query results as CSV or JSON.

**API direct query:**

```bash
curl -G "https://loki.example.com/loki/api/v1/query_range" \
  --data-urlencode 'query={app="api"} |= "ERROR"' \
  --data-urlencode "start=$(date -d '1 hour ago' +%s)000000000" \
  --data-urlencode "end=$(date +%s)000000000" \
  --data-urlencode "limit=5000" \
  -H "X-Scope-OrgID: my-tenant" | jq '.data.result[].values[]'
```

**Considerations for large exports:**

- Loki enforces `max_entries_limit_per_query` (default 5000). Paginate using the `start` parameter set to the timestamp of the last returned entry.
- Export jobs should run against query-frontend, not the ingester, to avoid impacting real-time log ingestion.
- For truly large exports (millions of lines), consider reading directly from the object store (S3) using the Loki chunks format — but this requires knowledge of the storage schema.

---

## AWS Environment Considerations

### Grafana Cloud with AWS Workloads

Grafana Cloud provides a managed Loki endpoint. The typical setup:

1. Deploy Grafana Agent (or Grafana Alloy) as a sidecar or daemonset in ECS/EKS.
2. Configure the agent to scrape container logs and add AWS metadata labels.
3. Push to the Grafana Cloud Loki endpoint using the provided API key.

The agent handles label mapping, but you must verify that the labels it attaches match what your dashboards and alert rules expect. Label mismatches between the agent config and Grafana dashboards are the top source of "empty query results" issues.

### Self-Hosted Loki on AWS

Running Loki on ECS or EKS with S3 as the chunk store is a common pattern. Key configuration areas that affect query behavior:

- **S3 bucket permissions:** Loki needs `s3:PutObject`, `s3:GetObject`, `s3:DeleteObject`, and `s3:ListBucket`. Missing `ListBucket` causes silent query failures for older chunks.
- **DynamoDB or BoltDB for index:** If using DynamoDB for the index store, ensure provisioned throughput is sufficient. Under-provisioned tables cause query timeouts that look like Loki bugs.
- **Compactor configuration:** The compactor merges index files. If it falls behind, queries over old data slow down progressively.

### Bridging CloudWatch and Loki

Some teams ship CloudWatch Logs to Loki for unified querying. This is done via Lambda subscription filters that forward log events to a Loki push endpoint. Be aware that this doubles your ingestion cost (CloudWatch ingestion + Loki ingestion) and introduces an additional delay of 1-5 seconds.

> **Skill:** For step-by-step procedures on querying CloudWatch Logs, use the `query-aws-logs` skill.

---

## Common Mistakes

| Mistake | Impact | Fix |
|---|---|---|
| Using request IDs or user IDs as labels | Stream explosion, ingester OOM | Extract at query time with `\| json` or `\| logfmt` |
| Querying with `{}` (empty selector) | Scans all streams, query rejected or times out | Always specify at least one label matcher |
| Assuming logs appear instantly | Missing recent logs in queries | Account for 5-30 second ingestion delay; extend query window |
| Ignoring tenant ID in multi-tenant setup | Empty results with no error | Verify `X-Scope-OrgID` matches between shipper and query client |
| Using CloudWatch-style substring search without stream selector | Slow or rejected queries | Always start with a label-based stream selector, then filter with `\|=` |
| Not escaping regex in label matchers | Matches more than intended | Use `\\` for literal dots and special characters in `=~` |
| Exporting without pagination | Hits entry limit, truncated results | Use `limit` parameter and paginate by timestamp |
| Running metric queries over 30+ days | Timeouts | Keep metric query ranges under 24 hours; use recording rules for long-range aggregation |

---

## References

- [Grafana Loki LogQL documentation](https://grafana.com/docs/loki/latest/logql/)
- [Grafana Agent configuration for AWS](https://grafana.com/docs/agent/latest/)
- [Loki storage configuration with S3](https://grafana.com/docs/loki/latest/storage/)
