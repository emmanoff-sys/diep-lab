# CIM REST API Reference

Base URL (deployed): `http://localhost:9204` (loopback-only, per
`docker-compose-cim.yml`). All `/cim/*` routes require authentication;
`/health` and `/metrics` do not.

## Authentication

`Authorization: Bearer <token>`. Tokens are configured via the
`CIM_API_KEYS` env var (`services/cim/config.py`,
`services/cim/auth.py`) — **not** `fastapi/auth.py`'s JWT/API-key system
(deliberately separate, see `CIM_MAPPING_GUIDE.md` §1 /
`LIMITATIONS.md`). Format: `token1=tenant-a,token2=tenant-b,token3=`
(comma-separated `token=tenant_id` pairs; an empty tenant after `=` means
**unscoped** — sees every tenant's data).

`docker-compose-cim.yml`'s default (override in production):

```
CIM_API_KEYS=diep-cim-dev-token-CHANGE-ME=,diep-cim-tenant-a-CHANGE-ME=sit-tenant,diep-cim-tenant-b-CHANGE-ME=sit-tenant-b
```

| Response | Meaning |
|---|---|
| `401 {"detail": "authentication required"}` | Missing/unknown/malformed Bearer token |
| `403` | Not used today — there is no role hierarchy, only tenant scope |
| `404` | Resource not found (or not visible to this token's tenant) |
| `400 {"error": "<reason>", "detail": "..."}` | A `CimValidationError` (bad `profile`, `node_type`, timestamp, or `limit`) |

## Pagination

Every list route accepts `limit` (default 100, max 1000) and `offset`
(default 0) query params. Out-of-range `limit` returns `400
invalid_limit`.

## Routes

| Method | Path | Query params | Notes |
|---|---|---|---|
| GET | `/health` | — | No auth. `{"status":"UP","service":"cim"}` |
| GET | `/metrics` | — | No auth. Prometheus exposition format, or `503` if `prometheus_client` isn't installed |
| GET | `/cim/end-devices` | `device_type`, `site_name`, `limit`, `offset` | |
| GET | `/cim/end-devices/{device_id}` | — | `404` if not found/not in scope |
| GET | `/cim/meters` | `site_name`, `limit`, `offset` | Only `device_type='smartmeter'` |
| GET | `/cim/meters/{device_id}` | — | |
| GET | `/cim/assets` | `der_type`, `vpp_group`, `limit`, `offset` | DER-only, see `LIMITATIONS.md` |
| GET | `/cim/assets/{der_id}` | — | |
| GET | `/cim/customers` | `priority`, `limit`, `offset` | |
| GET | `/cim/customers/{customer_id}` | — | |
| GET | `/cim/service-points` | `customer_id`, `node_id`, `limit`, `offset` | |
| GET | `/cim/service-points/{service_point_id}` | — | |
| GET | `/cim/usage-points` | `limit`, `offset` | Deduplicated — see `CIM_MAPPING_GUIDE.md` §2 |
| GET | `/cim/usage-points/{usage_point_id}` | — | `usage_point_id` is the synthesized `name` field (e.g. `UP-METER001`), not `mRID` |
| GET | `/cim/connectivity-nodes` | `node_type`, `site_name`, `limit`, `offset` | `node_type` validated against the live `grid_nodes` CHECK list |
| GET | `/cim/connectivity-nodes/{node_id}` | — | |
| GET | `/cim/terminals` | `edge_id`, `node_id`, `limit`, `offset` | Synthesized, no detail route (no single stored identity to fetch by) |
| GET | `/cim/transformers` | `site_name`, `limit`, `offset` | |
| GET | `/cim/transformers/{node_id}` | — | |
| GET | `/cim/feeders` | `site_name`, `limit`, `offset` | |
| GET | `/cim/feeders/{node_id}` | — | |
| GET | `/cim/measurements` | `device_id`, `measurement_type`, `limit`, `offset` | Definitions, not readings |
| GET | `/cim/measurement-values` | `device_id`, `measurement_type`, `since`, `until`, `limit`, `offset` | `since`/`until` are ISO 8601 (`Z` or `+00:00` suffix both accepted) |
| GET | `/cim/export/{object_type}` | `format` (`json`\|`xml`, default `json`), `profile` (`metering`\|`network`\|`measurements`\|`full`, default `full`), `limit`, `offset` | `{object_type}` is plural-kebab, matching the list routes (`meters`, `end-devices`, etc. — see `_EXPORT_REGISTRY` in `services/cim/api.py`). No per-type filters beyond `limit`/`offset` — list-then-export client-side for filtered output. |

## Example

```
curl -H "Authorization: Bearer diep-cim-tenant-a-CHANGE-ME" \
  "http://localhost:9204/cim/meters/SIT-METER-001"
```

```json
{
  "mRID": "8100e050-db49-546c-a74b-422cdd430723",
  "name": "SIT-METER-001",
  "description": null,
  "aliasName": null,
  "amrSystem": null,
  "isVirtual": false,
  "timeZoneOffset": null,
  "deviceType": "smartmeter",
  "status": "ONLINE",
  "siteName": "SIT Validation Site",
  "tenantId": "sit-tenant",
  "location": "SIT Validation Site",
  "feederMRID": "...",
  "transformerMRID": "...",
  "formNumber": null
}
```

```
curl -H "Authorization: Bearer diep-cim-dev-token-CHANGE-ME" \
  "http://localhost:9204/cim/export/meters?format=xml&profile=metering"
```

```xml
<?xml version="1.0" ?>
<rdf:RDF xmlns:rdf="http://www.w3.org/1999/02/22-rdf-syntax-ns#" xmlns:cim="http://diep.local/cim/spec-shaped#">
  <cim:Meter rdf:ID="8100e050-db49-546c-a74b-422cdd430723">
    <cim:Meter.name>SIT-METER-001</cim:Meter.name>
    <cim:Meter.deviceType>smartmeter</cim:Meter.deviceType>
    ...
  </cim:Meter>
</rdf:RDF>
```
