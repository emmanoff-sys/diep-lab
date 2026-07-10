# OA-098 — Connector Certificate Lifecycle

## Status

APPROVED (PAO-026)

## Scope

Certificate management guidance for the three external-integration connectors in
staging environments. This document covers the TLS certificate requirements for
SCADA (OPC-UA), GIS, and AMI connector authentication and transport security.
It does not authorise production certificate provisioning.

## Certificate Roles

### SCADA Connector (OPC-UA)

The OPC-UA protocol requires mutual TLS for secure channel establishment. Two
certificate roles apply:

- **Application certificate**: identifies the SCADA connector application to the
  OPC-UA server. Issued per connector instance. Used for session authentication.
- **Trust list**: the connector must trust the OPC-UA server certificate. The server
  must trust the connector application certificate.

Requirements:
- Certificate format: DER or PEM, depending on OPC-UA stack.
- Key usage: digitalSignature, keyEncipherment.
- Subject alternative name: must match the connector's application URI.
- Validity: minimum 1 year; alert at 60 days before expiry.

### GIS Connector

GIS connector authentication uses transport-level TLS to the GIS system endpoint.

- **CA trust**: the connector must trust the GIS system's TLS certificate chain.
- **Client certificate**: if the GIS system requires mutual TLS, a client certificate
  is required for the connector.

Requirements:
- Standard X.509 v3 TLS certificate.
- Validity: minimum 1 year; alert at 60 days before expiry.

### AMI Connector

AMI connector authentication uses transport-level TLS to the AMI system endpoint.

- **CA trust**: the connector must trust the AMI system's TLS certificate chain.
- **Client certificate**: if the AMI system requires mutual TLS, a client certificate
  is required for the connector.

Requirements:
- Standard X.509 v3 TLS certificate.
- Validity: minimum 1 year; alert at 60 days before expiry.

## Certificate Lifecycle Procedures

### Provisioning (staging)

1. Generate a certificate signing request (CSR) for each connector instance.
2. Submit the CSR to the staging certificate authority or use a self-signed certificate
   for staging validation only.
3. Install the certificate and private key in the connector configuration (secret
   reference, not plaintext in config file).
4. Confirm the connector can establish a TLS session using the provisioned certificate.
5. Record the certificate subject, serial number, issuer, and expiry date.

### Rotation

1. Generate a new CSR and obtain a new certificate before the existing certificate
   expires (target: 30 days before expiry).
2. Install the new certificate in the connector configuration.
3. Restart the connector and confirm TLS session establishment with the new certificate.
4. Confirm the old certificate can be revoked at the issuing CA.
5. Record rotation evidence: old serial, new serial, rotation timestamp.

### Expiry Monitoring

| Alert | Threshold |
| --- | --- |
| Warning | 60 days before expiry |
| Critical | 30 days before expiry |
| Emergency | 7 days before expiry |

Expiry monitoring shall be implemented as part of the connector observability layer.
The `connector_healthy` Gauge metric should reflect certificate validity where
certificate validation is part of the connector's health check.

### Revocation

If a certificate is suspected compromised:

1. Immediately stop the affected connector.
2. Revoke the certificate at the issuing CA.
3. Provision a replacement certificate following the provisioning procedure.
4. Record the revocation: reason, timestamp, affected connector(s), replacement.

## Staging Certificate Constraints

- Self-signed certificates are acceptable for staging validation.
- Staging certificates must not be promoted to production.
- Production certificates require a governed CA and a separate provisioning approval.
- Certificate private keys must never be stored in the repository or in plaintext
  configuration files.
