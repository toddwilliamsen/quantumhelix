# Common Information Model (CIM) Reference

Field-level mapping from AWS and Azure raw telemetry into Quantum Helix’s normalized `CloudSecurityEvent`.

---

## Canonical schema

```text
CloudSecurityEvent
├── timestamp              str
├── normalized_identity    str
├── source_ip              str
├── api_velocity           float      ┐
├── auth_failures          float      ├─► PCA feature vector inputs
├── data_volume_bytes      float      │
├── (source_ip → ip_hash)  float      ┘
├── cloud_provider         str        (enrichment)
└── raw_event_id           str        (enrichment / SIEM correlation)
```

Feature vector order used by `to_feature_vector()`:

1. `api_velocity`  
2. `auth_failures`  
3. `data_volume_bytes`  
4. IPv4 octet hash of `source_ip`  

---

## AWS mapping (`parse_aws`)

Typical sources: **CloudTrail**-style JSON (also compatible with flow-adjacent byte fields when present).

| CIM field | AWS source paths (priority order) | Notes |
|-----------|-----------------------------------|-------|
| `timestamp` | `eventTime` | Falls back to UTC now |
| `normalized_identity` | `userIdentity.arn` → `userIdentity.userName` | Default `aws:unknown` |
| `source_ip` | `sourceIPAddress` | Default `0.0.0.0` |
| `data_volume_bytes` | `additionalEventData.bytesTransferred` | Numeric cast |
| `auth_failures` | `authFailureCount` | Synthetic in mocks; extend for real error catalogs |
| `api_velocity` | `apiVelocity` or derived from `requestParameters` / `errorCode` | Mock sets explicitly |
| `cloud_provider` | constant `"AWS"` | |
| `raw_event_id` | `eventID` / `eventId` | |

### Example AWS fragment

```json
{
  "eventTime": "2026-07-15T15:00:00.000000Z",
  "eventID": "aws-evt-000042",
  "sourceIPAddress": "203.0.113.10",
  "userIdentity": {
    "arn": "arn:aws:iam::123456789012:user/ops-reader-1",
    "userName": "ops-reader-1"
  },
  "additionalEventData": { "bytesTransferred": 125000 },
  "apiVelocity": 8.5,
  "authFailureCount": 0
}
```

---

## Azure mapping (`parse_azure`)

Typical sources: **Activity Log** / **NSG Flow Log**-style JSON.

| CIM field | Azure source paths (priority order) | Notes |
|-----------|-------------------------------------|-------|
| `timestamp` | `time` → `TimeGenerated` → `eventTimestamp` | |
| `normalized_identity` | `claims.name` → `caller` / `Caller` | Default `azure:unknown` |
| `source_ip` | `srcIP_s` → `callerIpAddress` | |
| `data_volume_bytes` | `bytesOut_d` → `bytesOut` | |
| `auth_failures` | `authFailureCount`; if zero, `ResultType` failure strings → `1.0` | Does not clobber explicit counts |
| `api_velocity` | `apiVelocity` or derived from `properties` / `Level` | |
| `cloud_provider` | constant `"Azure"` | |
| `raw_event_id` | `correlationId` → `id` | |

### Example Azure fragment

```json
{
  "time": "2026-07-15T15:00:00.000000Z",
  "correlationId": "azure-corr-000042",
  "claims": { "name": "ops-reader-1@corp.local" },
  "srcIP_s": "198.51.100.20",
  "bytesOut_d": 250000,
  "apiVelocity": 6.0,
  "authFailureCount": 0,
  "ResultType": "Success"
}
```

---

## Fused / cross-cloud events

Validation Attack C constructs a CIM row directly:

| Field | Example |
|-------|---------|
| `cloud_provider` | `AWS+Azure` |
| `normalized_identity` | Azure actor mapped to AWS role ARN |
| numeric features | Extreme velocity / failures / bytes |

Use this pattern for correlation engines that emit a single pivot record after joining clouds upstream.

---

## Normal vs attack feature ranges (mock / validation)

| Feature | Normal (approx.) | Attack (approx.) |
|---------|------------------|------------------|
| `api_velocity` | 1 – 25 | 85 – 140 |
| `auth_failures` | 0 – 2 | 12 – 45 |
| `data_volume_bytes` | 10³ – 10⁶ | 10⁸ – 10⁹+ |

Correlated extremes across all three numeric signals are what the hybrid scorer treats as critical.

---

## IP hashing

`_ip_octet_hash` converts `A.B.C.D` to:

```text
A·256³ + B·256² + C·256 + D
```

Invalid IPs map to `0.0`. This is a **numeric embedding**, not geolocation or reputation enrichment.

---

## Extending the CIM

When adding fields:

1. Add optional dataclass attributes (defaults for back-compat).  
2. Update both parsers.  
3. Decide whether the field is **PCA input** or **alert enrichment only**.  
4. If it becomes a PCA input, increase `N_PRINCIPAL_COMPONENTS` **and** qubit count together.  
5. Update ASFF `Resources.Details` / CEF extensions in `alerter.py`.  
6. Extend `validate.py` attack/normal synthesizers.
