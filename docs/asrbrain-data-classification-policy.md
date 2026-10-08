# Data Classification Policy

- `confidential` + `local_only`: ARXML, C/H source, vendor docs (MICROSAR/TRESOS/EB/KPIT), OEM/customer requirements, credentials, VINs, private IPs, ECU topology.
- `internal` + `local_only` (default): anything ambiguous; cloud only after explicit reclassification.
- `public` + policy-controlled: generic AUTOSAR spec text explicitly marked public; still requires `cloud_allowed` tenant policy.
- Detectors (deterministic first): filename patterns, ARXML tags, C signatures, VIN/IP/email/API-key regex, vendor namespaces; local LLM only for ambiguous cases.
- Redaction: reversible token map (`<VIN_001>`, `<PROJECT_001>`, …) stored locally; never transmitted to cloud providers.
