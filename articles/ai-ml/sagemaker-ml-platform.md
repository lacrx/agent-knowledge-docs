---
title: SageMaker ML Platform
topics:
  - sagemaker
  - machine-learning
  - aws
  - terraform
  - infrastructure-as-code
skills:
  - provision-sagemaker-root
  - provision-sagemaker-training
  - provision-sagemaker-model-registry
summary: >
  Advisory guide for provisioning and operating AWS SageMaker as a managed ML platform —
  IAM design, training jobs, model registry, endpoint deployment, cost control, and governance.
aliases:
  - aws sagemaker
  - sagemaker training
  - ml platform aws
related:
  - bedrock-llm-integration
last-updated: 2026-06-25
---

# SageMaker ML Platform

## Overview

AWS SageMaker is a managed ML platform that handles the infrastructure for training models, storing artifacts, registering model versions, and deploying inference endpoints. Unlike Bedrock, which provides access to pre-built foundation models via API, SageMaker is for teams that train, fine-tune, or serve their own models and need control over the compute, data pipeline, and deployment lifecycle.

The platform spans multiple AWS services under one umbrella: S3 for artifact storage, ECR for container images, IAM for access control, CloudWatch for monitoring, and SageMaker-specific resources like training jobs, model packages, and endpoints. Understanding which pieces you actually need -- and in what order to provision them -- is the difference between a clean ML platform and a tangled mess of permissions and orphaned resources.

This article covers the architectural decisions, environment design, and operational boundaries you need to think through before writing Terraform. The companion skills handle the actual provisioning.

> **Skill:** For step-by-step provisioning of the foundational SageMaker resources, use the `provision-sagemaker-root` skill.

---

## SageMaker vs Bedrock — When to Use Which

The most common early mistake is choosing SageMaker when Bedrock would suffice, or vice versa. They solve different problems.

| Dimension | SageMaker | Bedrock |
|-----------|-----------|---------|
| Use case | Train/fine-tune/deploy custom models | Consume pre-built foundation models via API |
| Compute control | Full (instance types, spot, distributed) | None (serverless, managed by AWS) |
| Model ownership | You own the model artifacts | AWS hosts vendor models |
| Cost model | Pay for compute time + endpoints | Pay per token / per API call |
| Operational burden | High (IAM, networking, monitoring, scaling) | Low (API key + go) |
| Data residency | Your VPC, your S3 buckets | AWS-managed, region-scoped |
| Customization | Bring any framework, any container | Limited to supported models + fine-tuning |

**Decision rule:** If you are calling a foundation model and do not need to train your own, start with Bedrock. If you need custom training, proprietary models, or fine-grained control over serving infrastructure, use SageMaker. Many production systems use both -- Bedrock for general LLM tasks, SageMaker for specialized models trained on proprietary data.

---

## Core Platform Components

SageMaker is not a single service. It is a collection of resources that you provision and connect. Here is how they relate:

```
S3 (artifacts)  <---->  Training Job  ----> Model Package (Registry)
     ^                      |                       |
     |                      v                       v
ECR (containers)     CloudWatch Logs          Endpoint Config
                                                    |
                                                    v
                                               Endpoint (serving)
```

### IAM Roles

SageMaker requires at least two IAM roles:

| Role | Purpose | Trusted Principal |
|------|---------|-------------------|
| Execution role | Used by training jobs, endpoints, and notebooks to access S3, ECR, CloudWatch | `sagemaker.amazonaws.com` |
| Pipeline role | Used by SageMaker Pipelines to orchestrate multi-step workflows | `sagemaker.amazonaws.com` |

The execution role is the most critical. It needs:
- `s3:GetObject` / `s3:PutObject` on your artifact buckets
- `ecr:GetDownloadUrlForLayer` / `ecr:BatchGetImage` on your training container repos
- `logs:CreateLogStream` / `logs:PutLogEvents` for CloudWatch
- `sagemaker:CreateModel` / `sagemaker:CreateEndpoint` if jobs auto-deploy

A common mistake is giving the execution role `AdministratorAccess` during development and then struggling to scope it down later. Start with the minimum permissions and add as training jobs fail with `AccessDenied`.

### Artifact Storage (S3)

Every SageMaker workflow reads from and writes to S3. Typical bucket structure:

```
s3://project-ml-artifacts-{env}/
  training-data/
    dataset-v1/
    dataset-v2/
  model-artifacts/
    {job-name}/model.tar.gz
  pipeline-output/
    {execution-id}/
```

Use separate prefixes (not separate buckets) for training data, model artifacts, and pipeline outputs. A single bucket per environment keeps IAM policies simple and lifecycle rules manageable. Enable versioning -- you will want to recover a previous model artifact at some point.

### Training Containers (ECR)

SageMaker training jobs run inside Docker containers. You have three options:

1. **AWS pre-built images** -- For standard frameworks (PyTorch, TensorFlow, XGBoost). AWS maintains these and publishes image URIs per region.
2. **Extended images** -- Start from a pre-built image, add your dependencies. Best balance of convenience and control.
3. **Bring your own container (BYOC)** -- Full custom Dockerfile. Required for non-standard frameworks or proprietary code.

For options 2 and 3, you push to ECR. The execution role must have pull access to the ECR repo.

> **Skill:** For provisioning ECR repositories with the right lifecycle policies, use the `provision-ecr-repository` skill.

---

## Environment Design

### Multi-Environment Strategy

ML platforms need environment isolation just like application platforms, but the boundaries are different:

| Environment | Purpose | Training Compute | Endpoints |
|-------------|---------|-------------------|-----------|
| Dev | Experimentation, small-scale training | Small instances, spot | None or single-instance |
| Staging | Validation, integration testing | Production-like, smaller scale | Shadow or canary endpoints |
| Prod | Production training and serving | Full-scale, on-demand or reserved | Auto-scaled, multi-AZ |

Use separate AWS accounts per environment if your organization supports it. At minimum, use separate IAM roles and S3 buckets per environment. Never let a dev training job write to production S3 paths.

### Networking

SageMaker can run in two network modes:

- **Default (public)** -- SageMaker manages the network. Simpler but less secure.
- **VPC mode** -- Training jobs and endpoints run in your VPC subnets. Required for compliance, accessing private data stores, or connecting to on-premises systems.

VPC mode requires NAT gateways or VPC endpoints for SageMaker to reach S3, ECR, and CloudWatch. This is a common source of training job failures -- the job starts, cannot reach S3, and times out with an unhelpful error. Always provision VPC endpoints for `s3`, `ecr.api`, `ecr.dkr`, `logs`, and `sagemaker.api` if using VPC mode.

---

## Training Jobs

A training job is a transient compute resource that runs your training code, reads data from S3, and writes a model artifact back to S3.

### Key Parameters

```hcl
resource "aws_sagemaker_training_job" "example" {
  training_job_name = "my-model-${timestamp()}"
  role_arn          = aws_iam_role.sagemaker_execution.arn

  algorithm_specification {
    training_image = "${aws_ecr_repository.training.repository_url}:latest"
    training_input_mode = "File"  # or "Pipe" for streaming
  }

  resource_config {
    instance_type  = "ml.m5.xlarge"
    instance_count = 1
    volume_size_in_gb = 50
  }

  input_data_config {
    channel_name = "training"
    data_source {
      s3_data_source {
        s3_uri         = "s3://${aws_s3_bucket.artifacts.id}/training-data/"
        s3_data_type   = "S3Prefix"
      }
    }
  }

  output_data_config {
    s3_output_path = "s3://${aws_s3_bucket.artifacts.id}/model-artifacts/"
  }

  stopping_condition {
    max_runtime_in_seconds = 3600
  }
}
```

### Instance Selection

| Instance Family | Use Case | Spot Available | Notes |
|-----------------|----------|----------------|-------|
| ml.m5 | General purpose, small models | Yes | Good starting point |
| ml.c5 | CPU-intensive training | Yes | Feature engineering, XGBoost |
| ml.p3 / ml.p4d | GPU training, deep learning | Yes (with interruptions) | Expensive; use spot for experimentation |
| ml.g5 | GPU inference + training | Yes | Good price-performance for medium models |
| ml.trn1 | Large-scale training (Trainium) | No | AWS custom silicon, best for large models |

**Use spot instances for dev/experimentation.** They save 60-90% but can be interrupted. Set checkpointing so training can resume. Never use spot for production training runs that must complete on a deadline.

> **Skill:** For step-by-step training job provisioning with Terraform, use the `provision-sagemaker-training` skill.

---

## Model Registry

The SageMaker Model Registry provides versioned model storage with approval workflows. Think of it as a container registry but for ML models.

### Concepts

| Concept | Description |
|---------|-------------|
| Model Package Group | A collection of model versions (like a repo in ECR) |
| Model Package | A specific model version with metadata, metrics, and artifact location |
| Approval Status | `PendingManualApproval`, `Approved`, `Rejected` |
| Model Metrics | Accuracy, latency, data drift scores attached to each version |

### Workflow

1. Training job completes, writes `model.tar.gz` to S3
2. Register the artifact as a new Model Package in a Model Package Group
3. Attach validation metrics (accuracy, F1, latency benchmarks)
4. Set status to `PendingManualApproval`
5. Reviewer (human or automated) approves or rejects
6. Approved models become deployable to endpoints

This approval gate is the most important governance mechanism. Without it, any training job can push a model straight to production. Wire the approval status change to an EventBridge rule that triggers your deployment pipeline.

> **Skill:** For step-by-step model registry provisioning, use the `provision-sagemaker-model-registry` skill.

---

## Endpoint Deployment

SageMaker endpoints serve models for real-time inference. An endpoint consists of:

1. **Model** -- References the S3 artifact and container image
2. **Endpoint Configuration** -- Instance type, count, variant weights
3. **Endpoint** -- The running inference service

### Deployment Patterns

| Pattern | Description | When to Use |
|---------|-------------|-------------|
| Single model | One model behind one endpoint | Simple use cases, dev/staging |
| Multi-variant | Multiple model versions on one endpoint with traffic splitting | A/B testing, canary deployments |
| Multi-model | Multiple models loaded on the same instance | Cost optimization when models are small and traffic is low |
| Serverless | No persistent instances; cold-start on request | Infrequent, latency-tolerant workloads |
| Async | Request-response via S3 polling | Large payloads, long inference times |

For production, start with a single-model endpoint and add multi-variant when you need A/B testing. Serverless endpoints have cold-start latency of 1-2 minutes, so only use them for workloads where that is acceptable.

### Auto-Scaling

Configure auto-scaling based on `InvocationsPerInstance` or custom CloudWatch metrics:

```hcl
resource "aws_appautoscaling_target" "sagemaker" {
  service_namespace  = "sagemaker"
  resource_id        = "endpoint/${endpoint_name}/variant/AllTraffic"
  scalable_dimension = "sagemaker:variant:DesiredInstanceCount"
  min_capacity       = 1
  max_capacity       = 4
}

resource "aws_appautoscaling_policy" "sagemaker" {
  name               = "sagemaker-scaling"
  service_namespace  = "sagemaker"
  resource_id        = aws_appautoscaling_target.sagemaker.resource_id
  scalable_dimension = aws_appautoscaling_target.sagemaker.scalable_dimension
  policy_type        = "TargetTrackingScaling"

  target_tracking_scaling_policy_configuration {
    predefined_metric_specification {
      predefined_metric_type = "SageMakerVariantInvocationsPerInstance"
    }
    target_value = 100
  }
}
```

---

## Cost Control

SageMaker costs come from three places, and each requires a different strategy:

| Cost Source | Control Mechanism |
|-------------|-------------------|
| Training compute | Spot instances, `max_runtime_in_seconds`, right-size instances |
| Endpoint compute | Auto-scaling, serverless for low-traffic, delete unused endpoints |
| Storage (S3 + EBS) | Lifecycle policies, delete old artifacts, compress model files |

### Cost Guardrails in Terraform

```hcl
# Always set a max runtime on training jobs
stopping_condition {
  max_runtime_in_seconds = 7200  # 2 hours max
}

# Use managed spot training in dev
resource_config {
  instance_type  = "ml.m5.xlarge"
  instance_count = 1
  volume_size_in_gb = 30
}

# Enable spot for non-production
enable_managed_spot_training = true
max_wait_time_in_seconds     = 14400  # 4 hours including spot wait
```

Set AWS Budgets alerts for SageMaker spend. A forgotten endpoint running `ml.p3.2xlarge` costs roughly $100/day. Automate endpoint deletion in non-production environments using a scheduled Lambda or EventBridge rule.

---

## Provisioning Sequence

The order matters. SageMaker resources have hard dependencies:

```
1. IAM roles (execution role, pipeline role)
2. S3 bucket (artifact storage)
3. ECR repository (training containers)
4. VPC endpoints (if using VPC mode)
5. Model Package Group (registry)
6. Training job (produces model artifact)
7. Model (references artifact + container)
8. Endpoint configuration
9. Endpoint
```

In Terraform, steps 1-5 are infrastructure that rarely changes. Steps 6-9 are operational resources that change with each training run. Separate them into different Terraform modules or state files. The infrastructure module is applied once per environment; the operational resources are managed by your ML pipeline (SageMaker Pipelines, Step Functions, or Airflow).

> **Skill:** For the foundational infrastructure (steps 1-5), use the `provision-sagemaker-root` skill.

---

## Common Mistakes

| Mistake | Consequence | Fix |
|---------|-------------|-----|
| Overly broad IAM execution role | Security risk, hard to audit | Start minimal, add permissions as jobs fail |
| No `max_runtime_in_seconds` | Runaway training jobs with unlimited cost | Always set a stopping condition |
| Using on-demand instances in dev | 3-10x higher cost than necessary | Use managed spot training for experimentation |
| Skipping model registry | No audit trail, no approval gate | Always register models before deploying |
| Single S3 bucket across environments | Dev jobs corrupt production data | Separate buckets or strict prefix-based IAM policies per env |
| No VPC endpoints in VPC mode | Training jobs timeout with unclear errors | Provision endpoints for S3, ECR, CloudWatch, SageMaker API |
| Forgetting to delete dev endpoints | Ongoing compute charges for unused resources | Automate cleanup with scheduled Lambda |
| Hardcoding instance types | Cannot adapt to availability or cost changes | Use variables, allow per-environment overrides |
| Not enabling S3 versioning | Cannot recover previous model artifacts | Enable versioning on artifact buckets from day one |

---

## References

- AWS SageMaker Developer Guide: `docs.aws.amazon.com/sagemaker/latest/dg/`
- Terraform AWS Provider — SageMaker resources: `registry.terraform.io/providers/hashicorp/aws/latest/docs/resources/sagemaker_domain`
- SageMaker Pricing: `aws.amazon.com/sagemaker/pricing/`
- SageMaker Built-in Container Images: `docs.aws.amazon.com/sagemaker/latest/dg/pre-built-containers-frameworks-deep-learning.html`
