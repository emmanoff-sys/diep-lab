# Explain DERMS Action Endpoint

## Overview
The `POST /copilot/explain_derms_action` endpoint provides AI-assisted explanations
of DERMS actions, including context about the device state, telemetry history,
alarms, and certification data at the time of the action.

## Authentication
Requires valid JWT with tenant claim (if tenant isolation is enabled).

## Request

```json
{
  "action_id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
  "tenant": "acme"
}
```

## Response Fields
- `action_id`: The requested action ID
- `action_summary`: Key details about the action
- `explanation`: AI-generated explanation (when provider available)
- `device_context`: Device metadata and health status
- `telemetry_data`: Telemetry from ±30 minutes around action time
- `alarm_history`: Alarms from ±30 minutes around action time
- `certification_data`: Device certification test results