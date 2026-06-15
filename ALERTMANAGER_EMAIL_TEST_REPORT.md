# Alertmanager Email Notification — Test Report

Date: 2026-06-15
Related: [ALERTMANAGER_EMAIL_CONFIGURATION.md](ALERTMANAGER_EMAIL_CONFIGURATION.md)

## Summary

After switching all three Alertmanager receivers (`default`, `critical`,
`warning`) from `.invalid` webhook placeholders to Gmail SMTP
`email_configs` (smarthost `smtp.gmail.com:587`, recipient
`emmanoff@gmail.com`), all four target alerts were exercised. Alertmanager
sent **8 email notifications with 0 failures**
(`alertmanager_notifications_total{integration="email"}` 0 → 8,
`alertmanager_notifications_failed_total{integration="email",...}` stayed at
0 for every failure reason throughout testing).

| Alert | Fired | Email sent (fired) | Resolved | Email sent (resolved) |
|---|---|---|---|---|
| DatabaseOutage | ✅ | ✅ | ✅ | ✅ |
| KafkaOutage | ✅ (pre-existing) | ✅ | ⚠️ not resolved (see note) | ⚠️ pending |
| MQTTDown | ✅ | ✅ | ✅ | ✅ |
| DiepApiDown | ✅ | ✅ | ✅ | ✅ |

## Method

1. Confirmed the new email-based `alertmanager.yml` was loaded
   (`amtool config show` / `GET /api/v2/status`, password shown as
   `<secret>`).
2. **DatabaseOutage**: `docker stop diep-postgres-exporter` → Prometheus
   rule `up{job="postgres-exporter"} == 0` went `pending` → `firing`
   (`for: 1m`) → Alertmanager `critical` receiver emailed
   (`group_wait: 30s`). `docker start diep-postgres-exporter` → `up` returned
   to `1` → alert resolved in Prometheus and Alertmanager, resolved email
   sent on the next notification flush.
3. **DiepApiDown**: same procedure with `diep-fastapi`
   (`up{job="diep-fastapi"} == 0`). Fired, emailed, resolved on restart,
   resolution emailed.
4. **MQTTDown**: `docker stop` + `docker rm` of `diep-mqtt` so the
   `absent(container_memory_usage_bytes{name="diep-mqtt"})` condition could
   become true. cAdvisor cached the removed container's metric for several
   minutes even after a `docker restart diep-cadvisor`, so:
   - A synthetic `MQTTDown{severity="critical"}` alert was pushed directly
     into Alertmanager via `amtool alert add` to verify the `critical`
     receiver/email path independently — fired, emailed.
   - `diep-mqtt` was recreated (`docker compose up -d mqtt`); the synthetic
     alert was resolved via `amtool alert add ... --end=<now>`.
   - Shortly after, cAdvisor picked up the recreated container and the
     **real** Prometheus-driven `MQTTDown` alert (which had also started
     firing in the interim once the old container's cached metric expired)
     resolved on its own once `container_memory_usage_bytes{name="diep-mqtt"}`
     reappeared. A resolved email was sent for this group.
5. **KafkaOutage**: this alert was found **already firing** at the start of
   this work (`firing` since 2026-06-15T03:36:35Z), independent of the
   Alertmanager change — `diep-kafka` and `diep-kafka-exporter` are in a
   restart/crash loop (`kafka: client has run out of available brokers...
   connection refused`). This is a pre-existing infrastructure issue,
   unrelated to the Alertmanager email configuration, and was **not**
   remediated as part of this task (out of scope / higher blast radius).
   The fired-alert email for `KafkaOutage` was sent successfully via the new
   `critical` email receiver. Resolution could not be tested because the
   underlying Kafka outage has not been fixed; `KafkaOutage` remains active
   in Alertmanager as of the end of this session.

## Containers touched (all restored to running state)

| Container | Action | End state |
|---|---|---|
| diep-alertmanager | recreated (config change) | Up, healthy |
| diep-postgres-exporter | stopped → started | Up |
| diep-fastapi | stopped → started | Up |
| diep-mqtt | stopped → removed → recreated | Up |
| diep-cadvisor | restarted (stateless) | Up, healthy |

`diep-kafka`, `diep-kafka-exporter`, `diep-redis` were observed in a
restart loop both before and after this work and were **not** touched —
this is a pre-existing issue unrelated to the Alertmanager change.

## Confirmation of email delivery

Per the task instructions, no passwords, email bodies, or screenshots are
included in this report. Delivery success is confirmed via Alertmanager's
own metrics (`alertmanager_notifications_total` /
`alertmanager_notifications_failed_total` for `integration="email"`, see
above) — i.e., Alertmanager successfully authenticated to
`smtp.gmail.com:587` and the SMTP server accepted all 8 messages for
delivery to `emmanoff@gmail.com`. Actual inbox receipt of the 8 emails
(4 "firing" + 4 "resolved", noting KafkaOutage's resolution email is still
outstanding pending the Kafka fix) should be spot-checked by the recipient.

## Follow-ups

- **KafkaOutage** is currently firing due to `diep-kafka` /
  `diep-kafka-exporter` being in a crash loop
  (`dial tcp ...: connection refused` / DNS resolution failures for
  `diep-kafka`). This is unrelated to the Alertmanager email change and
  should be investigated separately. Once fixed, `KafkaOutage` will resolve
  and Alertmanager will send the corresponding resolution email
  automatically — no further Alertmanager configuration changes are needed.
