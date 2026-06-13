# Explain Device State Endpoint

## Overview
The `POST /copilot/explain_device_state` endpoint provides AI-assisted explanations
of a device's current operational state, including health status analysis and
telemetry context.

## Authentication
Requires valid JWT with tenant claim (if tenant isolation is enabled).

## Request


{
  "device_id": "BAT001",
  "tenant": "acme"
}
