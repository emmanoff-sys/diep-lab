# Alertmanager Email (Gmail SMTP) Configuration

Date: 2026-06-15
Scope: `diep-alertmanager` service (defined in `docker-compose.yml`, project `diep-lab`)

## 1. Audit of prior configuration

`alertmanager/alertmanager.yml` (pre-change) used three `webhook_configs` receivers
(`default`, `critical`, `warning`) all pointing at placeholder URLs under
`http://diep-alertmanager-webhook.invalid/...`. These were non-functional
placeholders (per the file's own comment, "until [real webhook endpoints are
configured] alerts route to a local null receiver so the routing tree itself
can be validated end-to-end").

Routing tree (`route:`) and the single `inhibit_rules` entry
(`DiepApiDown` inhibits `HighCommandFailureRate` when `severity` matches)
were already correct and have been preserved unchanged.

A backup of the original file was taken before any change:
`alertmanager/alertmanager.yml.bak.20260615035423`
(and `docker-compose.yml.bak.20260615035423` for the compose file).

## 2. New configuration approach

Alertmanager's YAML config does not support `${VAR}`-style environment
variable expansion natively, and we do not want to write the Gmail SMTP
password into a file tracked in this git repo. So:

- `alertmanager/alertmanager.yml.template` — the new Alertmanager config,
  with `__ALERT_SMTP_HOST__`, `__ALERT_SMTP_PORT__`, `__ALERT_SMTP_USER__`,
  `__ALERT_SMTP_PASSWORD__`, `__ALERT_RECEIVER_EMAIL__` placeholders. This
  file is tracked in git and contains **no secrets**.
- `alertmanager/entrypoint.sh` — container entrypoint that runs `sed` to
  substitute the placeholders with values from the container's environment
  (sourced from `.env` via `env_file:` in docker-compose), then `exec`s
  `alertmanager` against the rendered file. The rendered file
  (`/alertmanager/alertmanager.yml`, containing the real password) is written
  only inside the container's `/alertmanager` storage volume — it never
  touches the bind-mounted repo directory and is not committed to git.
- `docker-compose.yml` (`alertmanager` service): added `env_file: [.env]`,
  switched the entrypoint to the rendering script, and changed the bind
  mounts from the old single config file to the new template +
  entrypoint script (both mounted read-only).

The previous bind mount `./alertmanager/alertmanager.yml:/etc/alertmanager/alertmanager.yml`
was removed (that file is now superseded by the `.template` + entrypoint
mechanism; the old file remains on disk only as the timestamped `.bak`).

## 3. Receivers (placeholder → email)

All three receivers (`default`, `critical`, `warning`) now use
`email_configs` instead of `webhook_configs`:

```yaml
global:
  smtp_smarthost: '<ALERT_SMTP_HOST>:<ALERT_SMTP_PORT>'   # smtp.gmail.com:587
  smtp_from: '<ALERT_SMTP_USER>'
  smtp_auth_username: '<ALERT_SMTP_USER>'
  smtp_auth_password: '<ALERT_SMTP_PASSWORD>'             # from .env, never written to git
  smtp_require_tls: true

receivers:
  - name: default
    email_configs:
      - to: '<ALERT_RECEIVER_EMAIL>'
        send_resolved: true
  - name: critical
    email_configs:
      - to: '<ALERT_RECEIVER_EMAIL>'
        send_resolved: true
  - name: warning
    email_configs:
      - to: '<ALERT_RECEIVER_EMAIL>'
        send_resolved: true
```

Values are sourced at container start from `.env`:
`ALERT_SMTP_HOST`, `ALERT_SMTP_PORT`, `ALERT_SMTP_USER`, `ALERT_SMTP_PASSWORD`,
`ALERT_RECEIVER_EMAIL` (all five resolve to `smtp.gmail.com` / `587` /
`emmanoff@gmail.com` / `<redacted>` / `emmanoff@gmail.com` respectively).

## 4. Routing and inhibition (unchanged)

```yaml
route:
  receiver: default
  group_by: ['alertname', 'severity']
  group_wait: 30s
  group_interval: 5m
  repeat_interval: 4h
  routes:
    - match: { severity: critical }
      receiver: critical
      repeat_interval: 1h
    - match: { severity: warning }
      receiver: warning

inhibit_rules:
  - source_match: { alertname: DiepApiDown }
    target_match: { alertname: HighCommandFailureRate }
    equal: ['severity']
```

## 5. Files changed

| File | Change |
|---|---|
| `alertmanager/alertmanager.yml.template` | **New.** Templated config with email receivers (replaces `.invalid` webhooks). |
| `alertmanager/entrypoint.sh` | **New.** Renders template from env vars, execs Alertmanager. |
| `docker-compose.yml` | `alertmanager` service: added `env_file: .env`, new `entrypoint`, swapped volume mounts. |
| `alertmanager/alertmanager.yml.bak.20260615035423` | **New.** Backup of pre-change config. |
| `docker-compose.yml.bak.20260615035423` | **New.** Backup of pre-change compose file. |

## 6. Restart performed

Only the `alertmanager` service was recreated/restarted:

```
docker compose up -d --force-recreate alertmanager
```

No other DIEP services were affected. Verified via `amtool config show`
(inside the container) and `GET /api/v2/status` that the rendered config
loads cleanly with `smtp_smarthost: smtp.gmail.com:587`,
`smtp_auth_username: emmanoff@gmail.com`, and all three receivers using
`email_configs` with `to: emmanoff@gmail.com`. The SMTP password is reported
as `<secret>` by Alertmanager's own API and was redacted in all command
output/logs reviewed during this change.
