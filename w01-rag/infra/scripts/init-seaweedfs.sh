#!/bin/sh
# Create the S3 bucket and upload seed documents.
# Runs inside the amazon/aws-cli image, which has neither wget nor curl —
# so readiness is probed via the aws CLI itself.
set -e

ENDPOINT="${SEAWEEDFS_ENDPOINT:-http://seaweedfs:8333}"
BUCKET="${SEAWEEDFS_BUCKET:-dataops-lake}"

# AWS CLI needs credentials even for SeaweedFS — anything works.
export AWS_ACCESS_KEY_ID="${AWS_ACCESS_KEY_ID:-any}"
export AWS_SECRET_ACCESS_KEY="${AWS_SECRET_ACCESS_KEY:-any}"
export AWS_DEFAULT_REGION="${AWS_DEFAULT_REGION:-us-east-1}"

echo "Waiting for SeaweedFS S3 API at ${ENDPOINT}..."
attempts=0
until aws --endpoint-url "${ENDPOINT}" s3 ls >/dev/null 2>&1; do
    attempts=$((attempts + 1))
    if [ "${attempts}" -gt 60 ]; then
        echo "SeaweedFS S3 API not reachable after 60 attempts; aborting." >&2
        exit 1
    fi
    sleep 2
done

echo "Creating bucket s3://${BUCKET}..."
aws --endpoint-url "${ENDPOINT}" s3 mb "s3://${BUCKET}" 2>/dev/null || true

if [ -d /docs ]; then
    echo "Uploading seed documents from /docs..."
    aws --endpoint-url "${ENDPOINT}" s3 cp /docs/ "s3://${BUCKET}/" --recursive
fi

echo "SeaweedFS bucket '${BUCKET}' ready."
