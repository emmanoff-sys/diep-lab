#!/bin/sh
# K6 MinIO HA validation script.
# Runs inside a minio/mc container on diep-lab_diep-net.
# Usage (reference — executed step by step during validation):
#   docker run --rm --network diep-lab_diep-net \
#     -v $(pwd)/minio-ha-validation/scripts:/scripts \
#     minio/mc /scripts/validate-minio-ha.sh
set -eu

ALIAS="m"
ENDPOINT="http://minio-ha-0:9000"
USER="minio-ha-val"
PASS="ha-val-minio-2026"
BUCKET="diep-ha-test"
WAL_BUCKET="diep-wal-archive-ha-test"

mc alias set "${ALIAS}" "${ENDPOINT}" "${USER}" "${PASS}" >/dev/null
echo "[1] Cluster info:"
mc admin info "${ALIAS}"

echo ""
echo "[2] Create bucket ${BUCKET}:"
mc mb -p "${ALIAS}/${BUCKET}"

echo ""
echo "[3] Baseline write — upload 20 objects:"
for i in $(seq -w 1 20); do
  printf "k6-validation-object-%s content-%s" "$i" "$i" | \
    mc pipe "${ALIAS}/${BUCKET}/obj-${i}.txt"
done
mc ls "${ALIAS}/${BUCKET}" | wc -l

echo ""
echo "[4] Baseline read — verify sample object:"
mc cat "${ALIAS}/${BUCKET}/obj-01.txt"

echo ""
echo "[5] WAL archive simulation — create bucket and upload 10 WAL-named objects:"
mc mb -p "${ALIAS}/${WAL_BUCKET}"
for seg in $(seq -w 1 10); do
  printf "WAL-segment-data-%s" "$seg" | \
    mc pipe "${ALIAS}/${WAL_BUCKET}/0000000100000000000000${seg}"
done
mc ls "${ALIAS}/${WAL_BUCKET}" | wc -l

echo ""
echo "[DONE] Baseline checks complete. Proceed with node-failure drills manually."
