-- DIEP ADMS Phase 3 (P3-1) — bring the DNP3 RTU MGD900 under the governed control
-- plane. M7 (017) registered the RTU as a device + topology node but left it
-- ungovernable: not in der_assets (so OC-4 voltvar_dispatch can't target it) and
-- with no switchable breaker edge (so OC-2 switch_op can't island/reconnect it).
--
-- This migration closes both gaps with DATA ONLY — no handler changes. OC-2 already
-- maps a device-backed switch open->island / close->grid_connect (the microgrid
-- vocabulary, see oc_switch.py), and OC-4 maps a microgrid setpoint via
-- der.CURTAIL_MAP -> set_setpoint. All three are in the device's ALLOWED_COMMANDS.
-- Additive + idempotent.

-- 1) Register MGD900 as a controllable microgrid DER so OC-4 (voltvar_dispatch)
--    and the DERMS fleet view can address it. node_id binds it to its M1 node.
INSERT INTO der_assets (der_id, der_type, node_id, rated_kw, controllable, vpp_group, tenant_id) VALUES
    ('MGD900', 'microgrid', 'ND-MGD900', 250, TRUE, 'abuja-site-a', 'default')
ON CONFLICT (der_id) DO NOTHING;

-- 2) Model the RTU's grid-tie (islanding) breaker as a switchable, device-backed
--    edge BUS-01 -> ND-MGD900. Normally closed (RTU grid-connected). OC-2:
--      open  -> dispatches `island`        (microgrid runs islanded)
--      close -> dispatches `grid_connect`  (resynchronize + reconnect)
--    attrs.device_id routes the breaker command to the DNP3 driver; cmd_open/
--    cmd_close are explicit for clarity (they match OC-2's defaults).
INSERT INTO grid_edges
    (edge_id, from_node, to_node, edge_type, is_switchable, normally_closed, is_closed,
     rating_kw, attrs, tenant_id) VALUES
    ('E-MGD900-CB', 'BUS-01', 'ND-MGD900', 'switch', TRUE, TRUE, TRUE, 250,
     '{"device_id": "MGD900", "role": "islanding_breaker", "cmd_open": "island", "cmd_close": "grid_connect", "protocol": "dnp3"}'::jsonb,
     'default')
ON CONFLICT (edge_id) DO NOTHING;
