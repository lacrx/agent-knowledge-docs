---
title: AWS CloudWatch Logging and Monitoring
topics:
  - aws
  - cloudwatch
  - logging
  - monitoring
  - observability
skills:
  - query-aws-logs
summary: >
  Advisory guide to CloudWatch Logs and Metrics — when to use each, authentication patterns, Logs Insights queries, metric concepts, alarms, and export strategies.
aliases:
  - cloudwatch logs insights
  - aws monitoring
  - cloudwatch metrics alarms
related:
  - loki-query-troubleshooting
last-updated: 2026-06-25
---

# AWS CloudWatch Logging and Monitoring

## Overview

AWS CloudWatch is two distinct systems under one umbrella: **CloudWatch Logs** (unstructured or semi-structured text emitted by your applications and infrastructure) and **CloudWatch Metrics** (numeric time-series data points organized by namespace and dimensions). Most teams conflate the two, which leads to poor alerting, expensive log queries, and dashboards that answer the wrong questions.

Understanding the boundary between logs and metrics is the single most important design decision for operational visibility on AWS. Logs tell you *what happened* in detail; metrics tell you *how much* or *how fast* something is happening over time. You need both, but using the wrong one for a given task wastes money and delays diagnosis.

> **Skill:** For step-by-step log querying procedures including filter patterns and Insights queries, use the `query-aws-logs` skill.

---

## Logs vs. Metrics: When to Use Each

| Use Case | Logs | Metrics | Rationale |
|---|---|---|---|
| **Debugging a single request** | Primary | Supporting | You need the full trace/context from log lines |
| **Alerting on error rate** | Avoid | Primary | Metric filters or custom metrics are cheaper and faster than log queries |
| **Capacity planning** | Avoid | Primary | CPU, memory, request count are already emitted as metrics |
| **Audit trail** | Primary | Avoid | You need the who/what/when detail that metrics cannot capture |
| **Anomaly detection** | Supporting | Primary | CloudWatch Anomaly Detection works on metric data |
| **Cost analysis per request** | Primary | Supporting | Individual cost attribution requires per-request log context |

The general rule: if you can express the question as a number over time, use metrics. If you need to search for specific events or read contextual detail, use logs.

---

## Authentication and Access

CloudWatch uses the standard AWS credential chain. The most common patterns:

1. **IAM roles on compute** — EC2 instance profiles, ECS task roles, Lambda execution roles. Preferred for production workloads. No credentials to manage.
2. **SSO for local development** — Run `aws sso login --profile <profile-name>` to get temporary credentials. Set `AWS_PROFILE` in your shell or pass `--profile` to every CLI command.
3. **IAM user access keys** — Static credentials stored in `~/.aws/credentials`. Acceptable for CI/CD service accounts with tight IAM policies; avoid for human users.

### Minimum IAM Permissions

For read-only log access (the most common agent and developer need):

```json
{
  "Effect": "Allow",
  "Action": [
    "logs:DescribeLogGroups",
    "logs:DescribeLogStreams",
    "logs:GetLogEvents",
    "logs:FilterLogEvents",
    "logs:StartQuery",
    "logs:GetQueryResults",
    "logs:StopQuery"
  ],
  "Resource": "arn:aws:logs:*:ACCOUNT_ID:log-group:/ecs/*"
}
```

Scope the `Resource` to the narrowest log group prefix that covers your services. For metrics read access, add `cloudwatch:GetMetricData`, `cloudwatch:GetMetricStatistics`, `cloudwatch:ListMetrics`, and `cloudwatch:DescribeAlarms`.

---

## CloudWatch Logs Concepts

### Log Groups and Log Streams

A **log group** is a named container — typically one per application or service (e.g., `/ecs/my-api-prod`). Each log group contains **log streams**, which are sequences of events from a single source (a container instance, a Lambda invocation, etc.).

Retention is set per log group. The default is **never expire**, which means unbounded storage costs. Set an explicit retention policy (14, 30, or 90 days covers most operational needs).

### Filter Patterns

Filter patterns are the simplest way to search logs. They run server-side and are free (you pay only for data scanned). Two styles:

```bash
# Simple text match — find all lines containing "ERROR"
aws logs filter-log-events \
  --log-group-name /ecs/my-api-prod \
  --filter-pattern "ERROR" \
  --start-time $(date -d '1 hour ago' +%s000)

# JSON field match — find 5xx status codes in structured logs
aws logs filter-log-events \
  --log-group-name /ecs/my-api-prod \
  --filter-pattern '{ $.status_code >= 500 }'
```

Filter patterns are fast for simple searches but cannot aggregate, sort, or join. For anything analytical, use Logs Insights.

### Logs Insights

Logs Insights is a query language that runs over log data. It supports filtering, aggregation, sorting, and visualization. Queries are charged per GB scanned.

```
# Error rate by service over 5-minute bins
fields @timestamp, @message
| filter @message like /ERROR/
| stats count(*) as error_count by bin(5m)
| sort @timestamp desc
```

```
# P99 latency from structured JSON logs
fields @timestamp, request_duration_ms
| filter ispresent(request_duration_ms)
| stats pct(request_duration_ms, 99) as p99, avg(request_duration_ms) as avg_ms by bin(10m)
```

```
# Top 10 most frequent error messages
fields @message
| filter @message like /ERROR/
| stats count(*) as cnt by @message
| sort cnt desc
| limit 10
```

Key points about Insights:

- Queries scan data by time range. Narrow your time window to control cost.
- The `parse` command extracts fields from unstructured log lines using glob or regex patterns.
- Results are limited to 10,000 rows. Use `stats` aggregation for larger datasets.
- Queries timeout after 15 minutes. If you hit this, narrow the time range or simplify the query.

### Metric Filters

Metric filters bridge logs and metrics. They watch a log group for a pattern and increment a CloudWatch metric when matched. This is the correct way to build alerts from log content — do not poll logs with scheduled Insights queries for alerting purposes.

```bash
aws logs put-metric-filter \
  --log-group-name /ecs/my-api-prod \
  --filter-name "5xx-errors" \
  --filter-pattern '{ $.status_code >= 500 }' \
  --metric-transformations \
    metricName=5xxErrorCount,metricNamespace=MyApp,metricValue=1
```

---

## CloudWatch Metrics Concepts

### Namespaces and Dimensions

Every metric lives in a **namespace** (e.g., `AWS/ECS`, `AWS/RDS`, `Custom/MyApp`). AWS services publish to their own namespaces automatically.

**Dimensions** are key-value pairs that identify a specific metric source. For example, an ECS metric might have dimensions `ClusterName=prod` and `ServiceName=my-api`. The combination of namespace + metric name + dimensions uniquely identifies a time series.

| Concept | Purpose | Example |
|---|---|---|
| Namespace | Groups related metrics | `AWS/ECS`, `Custom/MyApp` |
| Metric name | What is being measured | `CPUUtilization`, `RequestCount` |
| Dimension | Which resource | `ServiceName=my-api` |
| Period | Aggregation interval | 60 seconds, 300 seconds |
| Statistic | Aggregation function | `Average`, `Sum`, `p99` |

### Statistics and Periods

A **period** is the time interval over which a statistic is computed. A **statistic** is the aggregation function applied to data points within that period.

Common statistics: `Average`, `Sum`, `Minimum`, `Maximum`, `SampleCount`, and extended statistics like `p50`, `p95`, `p99`.

Choosing the wrong statistic hides problems. For latency, use `p99` or `p95` — `Average` masks tail latency. For error counts, use `Sum` — `Average` is meaningless. For CPU utilization, `Average` is usually appropriate but check `Maximum` to catch spikes.

### Alarms

Alarms evaluate a metric against a threshold over a number of evaluation periods. An alarm has three states: `OK`, `ALARM`, and `INSUFFICIENT_DATA`.

```bash
aws cloudwatch put-metric-alarm \
  --alarm-name "high-5xx-rate" \
  --namespace Custom/MyApp \
  --metric-name 5xxErrorCount \
  --statistic Sum \
  --period 300 \
  --evaluation-periods 2 \
  --threshold 10 \
  --comparison-operator GreaterThanThreshold \
  --alarm-actions arn:aws:sns:us-east-1:ACCOUNT_ID:ops-alerts
```

This alarm fires when the sum of 5xx errors exceeds 10 in two consecutive 5-minute periods. The `--alarm-actions` parameter points to an SNS topic for notifications.

Design alarms around *sustained* problems, not transient spikes. Use multiple evaluation periods (2-3) to avoid alert fatigue from single-period blips.

---

## Exporting and Local Analysis

### CLI Export for Ad-Hoc Analysis

```bash
# Export Logs Insights results to JSON
QUERY_ID=$(aws logs start-query \
  --log-group-name /ecs/my-api-prod \
  --start-time $(date -d '24 hours ago' +%s) \
  --end-time $(date +%s) \
  --query-string 'fields @timestamp, @message | filter @message like /ERROR/ | limit 500' \
  --output text --query 'queryId')

# Poll for results (queries are async)
aws logs get-query-results --query-id "$QUERY_ID" --output json > results.json
```

### Metric Data Export

```bash
aws cloudwatch get-metric-data \
  --metric-data-queries '[{
    "Id": "cpu",
    "MetricStat": {
      "Metric": {
        "Namespace": "AWS/ECS",
        "MetricName": "CPUUtilization",
        "Dimensions": [
          {"Name": "ClusterName", "Value": "prod"},
          {"Name": "ServiceName", "Value": "my-api"}
        ]
      },
      "Period": 3600,
      "Stat": "Average"
    },
    "ReturnData": true
  }]' \
  --start-time $(date -d '7 days ago' -u +%Y-%m-%dT%H:%M:%S) \
  --end-time $(date -u +%Y-%m-%dT%H:%M:%S) \
  --output json > cpu_metrics.json
```

For stakeholder reporting, export metric data to JSON and process locally with `jq`, Python, or a notebook. CloudWatch dashboards are useful for real-time monitoring but are poor for building polished reports.

### S3 Export for Long-Term Retention

For logs that must be retained beyond the CloudWatch retention window (compliance, cost analysis), export log groups to S3:

```bash
aws logs create-export-task \
  --log-group-name /ecs/my-api-prod \
  --from $(date -d '30 days ago' +%s000) \
  --to $(date +%s000) \
  --destination my-log-archive-bucket \
  --destination-prefix "cloudwatch-exports/my-api-prod"
```

Exported logs are gzipped text. For queryable long-term storage, consider routing logs to S3 via Firehose and querying with Athena.

---

## Structured Logging

Unstructured log lines (`ERROR: something went wrong`) are cheap to emit but expensive to query. Structured JSON logs unlock the full power of Logs Insights field extraction:

```json
{"timestamp": "2026-06-25T10:00:00Z", "level": "ERROR", "service": "my-api", "request_id": "abc-123", "message": "database timeout", "duration_ms": 5023}
```

With structured logs, you can filter on any field (`| filter level = "ERROR"`), aggregate by field (`| stats count(*) by service`), and compute percentiles (`| stats pct(duration_ms, 99)`). The investment in structured logging pays for itself within the first incident investigation.

---

## Trade-offs and Common Mistakes

| Mistake | Why It Hurts | Better Approach |
|---|---|---|
| Alerting on Logs Insights queries via scheduled runs | Slow (minutes of delay), expensive (per-GB scanning), unreliable timing | Use metric filters to create metrics from log patterns, then alarm on the metric |
| Using `Average` statistic for latency alarms | Masks tail latency — p99 can spike while average stays flat | Use `p99` or `p95` extended statistics |
| Default log retention (never expire) | Unbounded cost growth; old logs rarely accessed | Set 30-90 day retention; export to S3 for compliance |
| One giant log group for all services | Insights queries scan the entire group, increasing cost and noise | One log group per service or per environment+service |
| Ignoring `INSUFFICIENT_DATA` alarm state | New metrics or missing data cause alarms to silently enter this state | Set `treat-missing-data` to `breaching` or `notBreaching` based on your intent |
| Hardcoding AWS credentials | Security risk, rotation burden | Use IAM roles on compute; `aws sso login` for local dev |
| Polling `get-query-results` without checking status | Insights queries are async; results may not be ready | Check the `status` field; only parse results when status is `Complete` |

---

## Related Articles

- **[loki-query-troubleshooting](../monitoring/loki-query-troubleshooting.md)** — Companion guide for Grafana Loki log querying; useful when workloads span AWS and non-AWS infrastructure.
