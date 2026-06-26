---
name: ecr-push-deploy
title: Build, Push to ECR, and Deploy to ECS/Fargate
type: skill
topics:
  - aws
  - ecr
  - ecs
  - fargate
  - docker
  - deployment
  - containers
summary: >
  Build a container image locally, authenticate Docker to Amazon ECR, tag and
  push the image with an immutable tag, then update an ECS/Fargate service to
  deploy the new image and verify rollout status.
references:
  - skills/provision-ecr-repository.md
  - skills/provision-fargate-task.md
  - articles/aws/fargate/deploying-nextjs-apps-to-fargate.md
  - articles/aws/fargate/deploying-python-web-apps-to-fargate.md
last-updated: 2026-06-25
---

# Build, Push to ECR, and Deploy to ECS/Fargate

Build a Docker image, push it to an ECR repository, update the ECS task
definition with the new image URI, and roll out a new deployment on an
ECS/Fargate service. Follow steps in order.

---

## Prerequisites

- Docker Engine installed and running locally
- AWS CLI v2 installed and configured with valid credentials
- `jq` installed (for JSON manipulation in CLI steps)
- ECR repository already provisioned (see `provision-ecr-repository`)
- ECS cluster, service, and task definition already provisioned (see `provision-fargate-task`)
- IAM permissions: `ecr:GetAuthorizationToken`, `ecr:BatchCheckLayerAvailability`,
  `ecr:PutImage`, `ecr:InitiateLayerUpload`, `ecr:UploadLayerPart`,
  `ecr:CompleteLayerUpload`, `ecs:DescribeServices`,
  `ecs:UpdateService`, `ecs:DescribeTaskDefinition`,
  `ecs:RegisterTaskDefinition`, `iam:PassRole`

---

## Steps

### Step 1: Set environment variables

Export all required variables. Replace placeholder values with actual values
for your environment. Never hard-code secrets in these commands.

```bash
export AWS_ACCOUNT_ID="123456789012"
export AWS_REGION="us-east-1"
export ECR_REPOSITORY_NAME="my-app"
export IMAGE_NAME="my-app"
export IMAGE_TAG="$(git rev-parse --short HEAD)-$(date +%Y%m%d%H%M%S)"
export DOCKERFILE_PATH="./Dockerfile"
export BUILD_CONTEXT="."
export ECS_CLUSTER_NAME="my-cluster"
export ECS_SERVICE_NAME="my-service"
export TASK_DEFINITION_FAMILY="my-task"
export CONTAINER_NAME="my-app"
```

### Step 2: Construct the repository URI and full image URI

```bash
export REPOSITORY_URI="${AWS_ACCOUNT_ID}.dkr.ecr.${AWS_REGION}.amazonaws.com/${ECR_REPOSITORY_NAME}"
export IMAGE_URI="${REPOSITORY_URI}:${IMAGE_TAG}"

echo "Repository URI: ${REPOSITORY_URI}"
echo "Image URI:      ${IMAGE_URI}"
```

### Step 3: Build the container image

Build the image locally using the specified Dockerfile and build context.

```bash
docker build \
  -t "${IMAGE_NAME}:${IMAGE_TAG}" \
  -f "${DOCKERFILE_PATH}" \
  "${BUILD_CONTEXT}"
```

### Step 4: Authenticate Docker to Amazon ECR

Use the AWS ECR login flow to obtain a temporary Docker authentication token.

```bash
aws ecr get-login-password --region "${AWS_REGION}" \
  | docker login \
      --username AWS \
      --password-stdin \
      "${AWS_ACCOUNT_ID}.dkr.ecr.${AWS_REGION}.amazonaws.com"
```

### Step 5: Tag the image for ECR

Apply the full ECR repository URI and tag to the locally built image.

```bash
docker tag "${IMAGE_NAME}:${IMAGE_TAG}" "${IMAGE_URI}"
```

### Step 6: Push the image to ECR

```bash
docker push "${IMAGE_URI}"
```

### Step 7: Verify the image exists in ECR

Confirm that the pushed image is present in the ECR repository with the
expected tag.

```bash
aws ecr describe-images \
  --region "${AWS_REGION}" \
  --repository-name "${ECR_REPOSITORY_NAME}" \
  --image-ids imageTag="${IMAGE_TAG}" \
  --query 'imageDetails[0].{digest:imageDigest,tags:imageTags,pushed:imagePushedAt,size:imageSizeInBytes}' \
  --output table
```

### Step 8: Retrieve the current task definition

Fetch the current task definition JSON and prepare it for registration with
the new image URI.

```bash
aws ecs describe-task-definition \
  --region "${AWS_REGION}" \
  --task-definition "${TASK_DEFINITION_FAMILY}" \
  --query 'taskDefinition' \
  --output json > /tmp/task-def-current.json
```

### Step 9: Update the container image in the task definition

Replace the image URI for the target container and strip fields that cannot
be included when registering a new task definition revision.

```bash
jq \
  --arg CONTAINER "${CONTAINER_NAME}" \
  --arg IMAGE "${IMAGE_URI}" \
  '.containerDefinitions |= map(
    if .name == $CONTAINER then .image = $IMAGE else . end
  ) | del(
    .taskDefinitionArn,
    .revision,
    .status,
    .requiresAttributes,
    .compatibilities,
    .registeredAt,
    .registeredBy
  )' \
  /tmp/task-def-current.json > /tmp/task-def-new.json
```

### Step 10: Register the new task definition revision

```bash
NEW_TASK_DEF_ARN=$(aws ecs register-task-definition \
  --region "${AWS_REGION}" \
  --cli-input-json file:///tmp/task-def-new.json \
  --query 'taskDefinition.taskDefinitionArn' \
  --output text)

echo "New task definition ARN: ${NEW_TASK_DEF_ARN}"
```

### Step 11: Update the ECS service to use the new task definition

```bash
aws ecs update-service \
  --region "${AWS_REGION}" \
  --cluster "${ECS_CLUSTER_NAME}" \
  --service "${ECS_SERVICE_NAME}" \
  --task-definition "${NEW_TASK_DEF_ARN}" \
  --query 'service.{serviceName:serviceName,taskDefinition:taskDefinition,desiredCount:desiredCount,runningCount:runningCount}' \
  --output table
```

### Step 12: Wait for the service to reach steady state

Monitor the deployment until the new tasks are running and the old tasks
are drained. This command blocks until the service stabilizes or times out
after 10 minutes.

```bash
aws ecs wait services-stable \
  --region "${AWS_REGION}" \
  --cluster "${ECS_CLUSTER_NAME}" \
  --services "${ECS_SERVICE_NAME}"

echo "Service ${ECS_SERVICE_NAME} has reached steady state."
```

### Step 13: Verify the deployment

Confirm that the running service references the expected task definition
and that all tasks are in the RUNNING state.

```bash
aws ecs describe-services \
  --region "${AWS_REGION}" \
  --cluster "${ECS_CLUSTER_NAME}" \
  --services "${ECS_SERVICE_NAME}" \
  --query 'services[0].{
    serviceName:serviceName,
    status:status,
    taskDefinition:taskDefinition,
    runningCount:runningCount,
    desiredCount:desiredCount,
    deployments:deployments[*].{
      status:status,
      taskDefinition:taskDefinition,
      runningCount:runningCount,
      desiredCount:desiredCount,
      rolloutState:rolloutState
    }
  }' \
  --output json
```

### Step 14: Export outputs

```bash
echo "---"
echo "image_uri:              ${IMAGE_URI}"
echo "repository_uri:         ${REPOSITORY_URI}"
echo "deployed_service_name:  ${ECS_SERVICE_NAME}"
echo "task_definition_arn:    ${NEW_TASK_DEF_ARN}"
echo "---"
```

---

## Examples

### Deploy with a git-sha tag

```bash
export AWS_ACCOUNT_ID="111222333444"
export AWS_REGION="us-west-2"
export ECR_REPOSITORY_NAME="api-service"
export IMAGE_NAME="api-service"
export IMAGE_TAG="$(git rev-parse --short HEAD)-$(date +%Y%m%d%H%M%S)"
export DOCKERFILE_PATH="./Dockerfile"
export BUILD_CONTEXT="."
export ECS_CLUSTER_NAME="production"
export ECS_SERVICE_NAME="api-service"
export TASK_DEFINITION_FAMILY="api-service-task"
export CONTAINER_NAME="api"

# Then run Steps 2 through 14 above.
```

### Deploy a multi-stage build from a subdirectory

```bash
export AWS_ACCOUNT_ID="111222333444"
export AWS_REGION="eu-west-1"
export ECR_REPOSITORY_NAME="worker"
export IMAGE_NAME="worker"
export IMAGE_TAG="v1.2.3-$(date +%Y%m%d%H%M%S)"
export DOCKERFILE_PATH="./services/worker/Dockerfile"
export BUILD_CONTEXT="./services/worker"
export ECS_CLUSTER_NAME="staging"
export ECS_SERVICE_NAME="worker-service"
export TASK_DEFINITION_FAMILY="worker-task"
export CONTAINER_NAME="worker"

# Then run Steps 2 through 14 above.
```

---

## Constraints

| Constraint | Rationale |
|---|---|
| Use `aws ecr get-login-password` (not `docker login` with long-lived credentials) | Temporary token valid for 12 hours; avoids storing registry passwords |
| Prefer immutable image tags (git SHA + timestamp) over `latest` | Ensures each deployment is traceable to a specific build; prevents silent overwrites |
| No secrets hard-coded in commands or environment variable exports | Credentials must come from AWS CLI profiles, IAM roles, or CI environment |
| Strip non-registerable fields from task definition JSON before re-registering | `taskDefinitionArn`, `revision`, `status`, etc. cause registration failures if included |
| Use `aws ecs wait services-stable` with default timeout | Blocks until deployment completes; prevents premature success signals |
| Verify image existence in ECR before updating the service | Catches push failures early before triggering a deployment |
| Register a new task definition revision rather than updating in place | Preserves rollback history; previous revisions remain available |
| Tag the local image with the full ECR URI before pushing | Docker requires the registry prefix to route the push correctly |
| Use `--cli-input-json` for task definition registration | Handles complex JSON payloads reliably; avoids shell quoting issues |

---

## Outputs

- Container image built, tagged, and pushed to ECR with an immutable tag
- `image_uri`: full ECR image URI including tag (e.g. `123456789012.dkr.ecr.us-east-1.amazonaws.com/my-app:abc1234-20260625120000`)
- `repository_uri`: ECR repository URI without tag
- `deployed_service_name`: name of the ECS service updated with the new image
- New ECS task definition revision registered with updated container image
- ECS/Fargate service updated and verified at steady state
