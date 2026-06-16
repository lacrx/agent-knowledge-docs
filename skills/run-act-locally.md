---
name: run-act-locally
title: Run Act Locally
type: skill
topics:
  - github-actions
  - docker
  - ci-cd
  - testing
  - act
summary: >
  Set up nektos/act to run GitHub Actions workflows locally on Linux using a
  custom Docker runner image. Covers building the image, configuring .actrc,
  sharing it via ECR, and common act commands.
references:
  - skills/provision-ecr-repository.md
  - skills/create-python-dockerfile.md
last-updated: 2026-06-15
---

# Run Act Locally

Set up nektos/act with a custom runner image so GitHub Actions workflows run
locally without pushing. Follow steps in order.

---

## Prerequisites

- Docker installed and running
- nektos/act installed (`curl -s https://raw.githubusercontent.com/nektos/act/master/install.sh | sudo bash`)
- Linux host (act supports macOS but this skill targets Linux)
- AWS CLI configured (only if pushing image to ECR)

---

## Steps

### Step 1: Create the custom runner Dockerfile

Save as `.github/local/Dockerfile.act`:

```dockerfile
FROM ubuntu:22.04

ENV DEBIAN_FRONTEND=noninteractive

RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    git \
    jq \
    sudo \
    ca-certificates \
    gnupg \
    software-properties-common \
    && rm -rf /var/lib/apt/lists/*

# Node 20
RUN curl -fsSL https://deb.nodesource.com/setup_20.x | bash - && \
    apt-get install -y --no-install-recommends nodejs && \
    rm -rf /var/lib/apt/lists/*

# Python 3.12
RUN add-apt-repository ppa:deadsnakes/ppa && \
    apt-get update && \
    apt-get install -y --no-install-recommends \
    python3.12 \
    python3.12-venv \
    python3.12-dev \
    && rm -rf /var/lib/apt/lists/* && \
    update-alternatives --install /usr/bin/python3 python3 /usr/bin/python3.12 1 && \
    update-alternatives --install /usr/bin/python python /usr/bin/python3.12 1

# uv
RUN curl -LsSf https://astral.sh/uv/install.sh | sh && \
    mv /root/.local/bin/uv /usr/local/bin/uv && \
    mv /root/.local/bin/uvx /usr/local/bin/uvx

# Runner user (act expects this)
RUN useradd -m -s /bin/bash runner && \
    echo "runner ALL=(ALL) NOPASSWD:ALL" >> /etc/sudoers

USER runner
WORKDIR /home/runner
```

### Step 2: Build the image

```bash
docker build -t act-runner:latest -f .github/local/Dockerfile.act .
```

### Step 3: Sanity-check the image

```bash
docker run --rm act-runner:latest bash -c "\
  node --version && \
  python --version && \
  uv --version && \
  git --version && \
  jq --version && \
  echo 'All tools present'"
```

Expected output: version strings for Node 20.x, Python 3.12.x, uv, git, jq.

### Step 4: Create .actrc

Save as `~/.actrc` (global) or `.github/local/actrc` (per-repo, copy to `~/.actrc`):

```
-P ubuntu-latest=act-runner:latest
-P ubuntu-22.04=act-runner:latest
--pull=false
```

`--pull=false` uses the local image — faster startup and works offline.

Per-repo setup:

```bash
cp .github/local/actrc ~/.actrc
```

### Step 5: Create build-act-runner.sh for teammates

Save as `.github/local/build-act-runner.sh`:

```bash
#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
IMAGE_NAME="act-runner:latest"

echo "Building ${IMAGE_NAME}..."
docker build -t "${IMAGE_NAME}" -f "${SCRIPT_DIR}/Dockerfile.act" "${SCRIPT_DIR}/../.."

echo "Sanity check..."
docker run --rm "${IMAGE_NAME}" bash -c "node --version && python --version && uv --version"

if [ ! -f ~/.actrc ]; then
  cp "${SCRIPT_DIR}/actrc" ~/.actrc
  echo "Installed ~/.actrc"
else
  echo "~/.actrc already exists — compare with ${SCRIPT_DIR}/actrc and merge manually"
fi

echo "Done. Run 'act --list' to verify."
```

```bash
chmod +x .github/local/build-act-runner.sh
```

### Step 6: (Optional) Push image to ECR

```bash
AWS_ACCOUNT_ID="<AWS_ACCOUNT_ID>"
AWS_REGION="<AWS_REGION>"
ECR_REPO_NAME="<ECR_REPO_NAME>"
REGISTRY="${AWS_ACCOUNT_ID}.dkr.ecr.${AWS_REGION}.amazonaws.com"

aws ecr get-login-password --region "${AWS_REGION}" \
  | docker login --username AWS --password-stdin "${REGISTRY}"

docker tag act-runner:latest "${REGISTRY}/${ECR_REPO_NAME}:latest"
docker push "${REGISTRY}/${ECR_REPO_NAME}:latest"
```

Teammates pull instead of building:

```bash
aws ecr get-login-password --region "<AWS_REGION>" \
  | docker login --username AWS --password-stdin "<AWS_ACCOUNT_ID>.dkr.ecr.<AWS_REGION>.amazonaws.com"

docker pull "<AWS_ACCOUNT_ID>.dkr.ecr.<AWS_REGION>.amazonaws.com/<ECR_REPO_NAME>:latest"
docker tag "<AWS_ACCOUNT_ID>.dkr.ecr.<AWS_REGION>.amazonaws.com/<ECR_REPO_NAME>:latest" act-runner:latest
```

### Step 7: Common act commands

```bash
# List all jobs in all workflows
act --list

# Dry-run (parse only, no execution)
act -n

# Run all push-triggered workflows
act push

# Run a specific job
act -j validate-and-index

# Run a specific workflow file
act -W .github/workflows/validate-and-index.yml

# Pass secrets (from file — never inline in shell history)
act push --secret-file .secrets

# Pass a single env var
act push --env MY_VAR=value

# Verbose output for debugging
act push -v
```

### Step 8: Guard unsupported steps in workflows

Some GitHub Actions features don't work in act. Guard them:

```yaml
- name: Configure AWS credentials
  if: ${{ !env.ACT }}
  uses: aws-actions/configure-aws-credentials@v4
  with:
    role-to-assume: ${{ secrets.AWS_ROLE_ARN }}
    aws-region: us-east-1

- name: Reusable workflow call
  if: ${{ !env.ACT }}
  uses: ./.github/workflows/shared.yml
```

Act sets `env.ACT=true` automatically. Use this to skip OIDC auth, reusable
workflow calls, and any step that requires GitHub-hosted runner features.

---

## Constraints

| Constraint | Rationale |
|---|---|
| `--pull=false` recommended | Uses local image — faster startup, works offline, avoids Docker Hub rate limits |
| Never commit `.secrets` | Add to `.gitignore`; use `--secret-file` to pass secrets at runtime |
| Guard OIDC / reusable-workflow steps with `if: ${{ !env.ACT }}` | These features require GitHub infrastructure and fail under act |
| Run `act --list` before every `act` run | Catches YAML parse errors and confirms job names before execution |
| ECR tokens expire in 12 hours | Re-run `aws ecr get-login-password` if pull/push fails with auth errors |
| Keep runner image in sync with CI | When CI adds a dependency, update Dockerfile.act to match |

---

## Outputs

- Custom Docker runner image (`act-runner:latest`) with Node 20, Python 3.12, uv, git, jq
- `~/.actrc` mapping `ubuntu-latest` and `ubuntu-22.04` to local image
- `.github/local/build-act-runner.sh` setup script for teammates
- Runner image optionally pushed to ECR for team sharing
