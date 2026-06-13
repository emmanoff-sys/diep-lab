# DIEP Kubernetes manifests (Phase 9K — production HA target)

These deliver the HA architecture in `DIEP_HA_ARCHITECTURE.md` on a real ≥3-node cluster.
The single-host lab proves the **stateless API HA + Redis replication** patterns live
(`docker-compose-ha.yml`); these manifests deliver the **stateful** HA that a single host
cannot.

## Layout
- `secrets.example.yaml` — secret template (use sealed-secrets / External Secrets / Vault in prod).
- `api.yaml` — FastAPI **Deployment (replicas: 3) + Service + HPA + Ingress + PDB**.
  This is the production form of the lab's load-balanced replica tier (verified live).
- `postgres-cnpg.yaml` — TimescaleDB via the **CloudNativePG** operator (1 primary + 2
  replicas, automatic failover, WAL archiving + PITR).
- `redis.yaml` — Redis with **Sentinel** (auto-failover) — the production form of the lab's
  live primary+replica.
- `kafka-strimzi.yaml` — Kafka via the **Strimzi** operator (3 brokers, RF=3, min.insync=2).

## Deploy (order)
```bash
# operators (once per cluster)
kubectl apply -f https://raw.githubusercontent.com/cloudnative-pg/cloudnative-pg/release-1.23/releases/cnpg-1.23.0.yaml
kubectl create -f 'https://strimzi.io/install/latest?namespace=diep'
helm install redis bitnami/redis -f redis.yaml   # or apply redis.yaml CR

kubectl apply -f secrets.example.yaml     # after editing / via sealed-secrets
kubectl apply -f postgres-cnpg.yaml
kubectl apply -f kafka-strimzi.yaml
kubectl apply -f api.yaml
```

## Notes
- The API image is built from `fastapi/` (CI builds + signs it — Phase 10B). `app.py` already
  reads all config from env (9J-S0) and exposes `/healthz` + `/readyz` (9K), so it is
  orchestration-native with no code change.
- MQTT (clustered EMQX/HiveMQ + per-device mTLS), MinIO distributed, and the TLS Ingress
  cert issuer (cert-manager) are environment-specific and tracked in the HA architecture doc.
