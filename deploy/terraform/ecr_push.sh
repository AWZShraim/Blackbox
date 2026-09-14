#!/usr/bin/env bash
# Builds and pushes all four service images to the ECR repositories the
# ecr module created. Run after `terraform apply -target=module.ecr` (so
# the repos exist) and before the first full apply (so the task
# definitions have something real to pull). Usage:
#   ./ecr_push.sh <profile: demo|reference> <aws-account-id> <aws-region>
set -euo pipefail

PROFILE="${1:?usage: ecr_push.sh <profile> <account-id> <region>}"
ACCOUNT_ID="${2:?usage: ecr_push.sh <profile> <account-id> <region>}"
REGION="${3:?usage: ecr_push.sh <profile> <account-id> <region>}"
NAME_PREFIX="blackbox-${PROFILE}"
REPO_BASE="${ACCOUNT_ID}.dkr.ecr.${REGION}.amazonaws.com"

cd "$(dirname "$0")/../.."   # repo root

aws ecr get-login-password --region "$REGION" \
  | docker login --username AWS --password-stdin "$REPO_BASE"

docker build -f deploy/docker/backend.Dockerfile -t "${REPO_BASE}/${NAME_PREFIX}-mediator:latest" .
docker build -f deploy/docker/backend.Dockerfile -t "${REPO_BASE}/${NAME_PREFIX}-recorder:latest" .
docker build -f deploy/docker/backend.Dockerfile -t "${REPO_BASE}/${NAME_PREFIX}-demo:latest" .
docker build -f investigator/Dockerfile -t "${REPO_BASE}/${NAME_PREFIX}-investigator:latest" investigator

for svc in mediator recorder demo investigator; do
  docker push "${REPO_BASE}/${NAME_PREFIX}-${svc}:latest"
done

echo "Pushed. Update deploy/terraform/envs/${PROFILE}.tfvars's *_image values to:"
for svc in mediator recorder demo investigator; do
  echo "  ${svc}_image = \"${REPO_BASE}/${NAME_PREFIX}-${svc}:latest\""
done
