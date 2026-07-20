#!/usr/bin/env python3
"""
Generate Quantum Helix–compatible Azure dummy telemetry files.

Produces Activity Log–style and NSG Flow–style JSON/NDJSON that map cleanly
through ``normalization.MultiCloudLogParser.parse_azure``.

Used by ``azure/deploy_dummy_data.sh`` before blob upload.
"""

from __future__ import annotations

import argparse
import json
import random
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def iso(dt: datetime) -> str:
    return dt.strftime("%Y-%m-%dT%H:%M:%S.%fZ")


def random_ip(rng: random.Random, *, suspicious: bool = False) -> str:
    if suspicious:
        # Documentation / known-suspicious-looking ranges for demos
        return rng.choice(
            [
                f"185.220.{rng.randint(100, 110)}.{rng.randint(1, 254)}",
                f"45.33.{rng.randint(1, 50)}.{rng.randint(1, 254)}",
                f"203.0.113.{rng.randint(1, 254)}",
            ]
        )
    return (
        f"{rng.randint(10, 200)}.{rng.randint(0, 255)}."
        f"{rng.randint(0, 255)}.{rng.randint(1, 254)}"
    )


def activity_event(
    rng: random.Random,
    *,
    index: int,
    anomalous: bool,
    subscription_id: str,
    resource_group: str,
    when: datetime,
) -> Dict[str, Any]:
    if anomalous:
        identity = f"attacker-escalation-{index}@corp.local"
        api_velocity = rng.uniform(90.0, 130.0)
        auth_failures = rng.uniform(15.0, 40.0)
        bytes_out = rng.uniform(4e8, 2.2e9)
        operation = "Microsoft.Authorization/roleAssignments/write"
        level = "Error"
        result = "Failed"
        status = "403"
    else:
        identity = f"ops-user-{rng.randint(1, 25)}@corp.local"
        api_velocity = rng.uniform(1.0, 18.0)
        auth_failures = 0.0
        bytes_out = rng.uniform(5e3, 3e6)
        operation = rng.choice(
            [
                "Microsoft.Compute/virtualMachines/read",
                "Microsoft.Storage/storageAccounts/listKeys/action",
                "Microsoft.Network/networkSecurityGroups/read",
                "Microsoft.Resources/subscriptions/resourceGroups/read",
            ]
        )
        level = "Informational"
        result = "Success"
        status = "200"

    corr = str(uuid.uuid4())
    return {
        "id": (
            f"/subscriptions/{subscription_id}/resourceGroups/{resource_group}"
            f"/providers/Microsoft.Insights/events/qs-azure-act-{index:06d}"
        ),
        "correlationId": corr,
        "time": iso(when),
        "TimeGenerated": iso(when),
        "operationName": operation,
        "Level": level,
        "ResultType": result,
        "caller": identity,
        "claims": {"name": identity},
        "callerIpAddress": random_ip(rng, suspicious=anomalous),
        "srcIP_s": random_ip(rng, suspicious=anomalous),
        "bytesOut_d": bytes_out,
        "bytesOut": bytes_out,
        "apiVelocity": api_velocity,
        "authFailureCount": auth_failures,
        "category": "Administrative",
        "resourceGroupName": resource_group,
        "subscriptionId": subscription_id,
        "properties": {
            "resource": f"/subscriptions/{subscription_id}/resourceGroups/{resource_group}",
            "statusCode": status,
            "eventCategory": "Administrative",
            "quantumSafeguardLabel": "attack" if anomalous else "normal",
        },
    }


def nsg_flow_event(
    rng: random.Random,
    *,
    index: int,
    anomalous: bool,
    subscription_id: str,
    resource_group: str,
    when: datetime,
) -> Dict[str, Any]:
    """NSG flow–adjacent record using the same CIM field names ``parse_azure`` expects."""
    if anomalous:
        identity = f"exfil-flow-actor-{index}@corp.local"
        api_velocity = rng.uniform(95.0, 140.0)
        auth_failures = rng.uniform(10.0, 30.0)
        bytes_out = rng.uniform(8e8, 2.5e9)
        dest_port = 443
        decision = "Allow"
    else:
        identity = f"workload-nic-{rng.randint(1, 12)}@corp.local"
        api_velocity = rng.uniform(1.0, 15.0)
        auth_failures = 0.0
        bytes_out = rng.uniform(2e3, 2e6)
        dest_port = rng.choice([22, 80, 443, 3389])
        decision = rng.choice(["Allow", "Allow", "Deny"])

    src = random_ip(rng, suspicious=anomalous)
    return {
        "id": f"qs-nsg-flow-{index:06d}",
        "correlationId": str(uuid.uuid4()),
        "time": iso(when),
        "TimeGenerated": iso(when),
        "operationName": "Microsoft.Network/networkSecurityGroups/writeFlowLog",
        "Level": "Error" if anomalous else "Informational",
        "ResultType": "Failed" if anomalous and auth_failures > 20 else "Success",
        "caller": identity,
        "claims": {"name": identity},
        "srcIP_s": src,
        "callerIpAddress": src,
        "bytesOut_d": bytes_out,
        "apiVelocity": api_velocity,
        "authFailureCount": auth_failures,
        "properties": {
            "subscriptionId": subscription_id,
            "resourceGroup": resource_group,
            "nsg": f"{resource_group}-nsg",
            "flowDecision": decision,
            "destPort": dest_port,
            "protocol": "T",
            "quantumSafeguardLabel": "attack" if anomalous else "normal",
        },
    }


def attack_catalog(
    subscription_id: str,
    resource_group: str,
    when: datetime,
) -> List[Dict[str, Any]]:
    """Three named attacks aligned with ``validate.py`` scenarios (Azure-side)."""
    return [
        {
            "scenario": "Attack B — Azure Privilege Escalation",
            "event": {
                "id": f"/subscriptions/{subscription_id}/events/attack-b-azure-priv-esc",
                "correlationId": "attack-b-azure-priv-esc",
                "time": iso(when),
                "TimeGenerated": iso(when),
                "operationName": "Microsoft.Authorization/roleAssignments/write",
                "Level": "Error",
                "ResultType": "Failed",
                "caller": "attacker-escalation@corp.local",
                "claims": {"name": "attacker-escalation@corp.local"},
                "srcIP_s": "45.33.32.156",
                "callerIpAddress": "45.33.32.156",
                "bytesOut_d": 4.2e8,
                "apiVelocity": 97.0,
                "authFailureCount": 28.0,
                "properties": {
                    "statusCode": "403",
                    "rbacAction": "Microsoft.Authorization/roleAssignments/write",
                    "deniedRole": "Owner",
                    "quantumSafeguardLabel": "attack",
                    "resourceGroup": resource_group,
                },
            },
        },
        {
            "scenario": "Attack C — Cross-Cloud Pivoting (Azure leg)",
            "event": {
                "id": f"/subscriptions/{subscription_id}/events/attack-c-cross-cloud-pivot-azure",
                "correlationId": "attack-c-cross-cloud-pivot",
                "time": iso(when),
                "TimeGenerated": iso(when),
                "operationName": "Microsoft.Storage/storageAccounts/listKeys/action",
                "Level": "Error",
                "ResultType": "Failed",
                "caller": "pivot-actor@corp.local",
                "claims": {"name": "pivot-actor@corp.local"},
                "srcIP_s": "203.0.113.88",
                "bytesOut_d": 2.4e9,
                "apiVelocity": 134.0,
                "authFailureCount": 41.0,
                "properties": {
                    "statusCode": "403",
                    "quantumSafeguardLabel": "attack",
                    "pivotTarget": "arn:aws:iam::123456789012:role/CrossAccountAdmin",
                    "resourceGroup": resource_group,
                },
            },
        },
        {
            "scenario": "Azure Credential Stuffing & Exfiltration",
            "event": {
                "id": f"/subscriptions/{subscription_id}/events/attack-azure-credstuff-exfil",
                "correlationId": "attack-azure-credstuff-exfil",
                "time": iso(when),
                "TimeGenerated": iso(when),
                "operationName": "Microsoft.Storage/storageAccounts/blobServices/containers/blobs/read",
                "Level": "Error",
                "ResultType": "Failed",
                "caller": "svc-compromised-ci@corp.local",
                "claims": {"name": "svc-compromised-ci@corp.local"},
                "srcIP_s": "185.220.101.47",
                "bytesOut_d": 1.85e9,
                "apiVelocity": 118.0,
                "authFailureCount": 37.0,
                "properties": {
                    "statusCode": "403",
                    "quantumSafeguardLabel": "attack",
                    "resourceGroup": resource_group,
                },
            },
        },
    ]


def write_ndjson(path: Path, records: List[Dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        for record in records:
            handle.write(json.dumps(record, separators=(",", ":")) + "\n")


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate Azure dummy telemetry for Quantum Helix")
    parser.add_argument("--out-dir", type=Path, required=True, help="Output directory for JSON/NDJSON")
    parser.add_argument("--subscription-id", required=True)
    parser.add_argument("--resource-group", required=True)
    parser.add_argument("--normal-count", type=int, default=40)
    parser.add_argument("--attack-count", type=int, default=5)
    parser.add_argument("--seed", type=int, default=42)
    args = parser.parse_args()

    rng = random.Random(args.seed)
    now = utc_now()
    out: Path = args.out_dir
    out.mkdir(parents=True, exist_ok=True)

    activity_normal: List[Dict[str, Any]] = []
    activity_attack: List[Dict[str, Any]] = []
    nsg_normal: List[Dict[str, Any]] = []
    nsg_attack: List[Dict[str, Any]] = []

    for i in range(args.normal_count):
        when = now - timedelta(minutes=rng.randint(1, 240))
        activity_normal.append(
            activity_event(
                rng,
                index=i,
                anomalous=False,
                subscription_id=args.subscription_id,
                resource_group=args.resource_group,
                when=when,
            )
        )
        nsg_normal.append(
            nsg_flow_event(
                rng,
                index=i,
                anomalous=False,
                subscription_id=args.subscription_id,
                resource_group=args.resource_group,
                when=when,
            )
        )

    for i in range(args.attack_count):
        when = now - timedelta(minutes=rng.randint(1, 60))
        activity_attack.append(
            activity_event(
                rng,
                index=10_000 + i,
                anomalous=True,
                subscription_id=args.subscription_id,
                resource_group=args.resource_group,
                when=when,
            )
        )
        nsg_attack.append(
            nsg_flow_event(
                rng,
                index=10_000 + i,
                anomalous=True,
                subscription_id=args.subscription_id,
                resource_group=args.resource_group,
                when=when,
            )
        )

    catalog = attack_catalog(args.subscription_id, args.resource_group, now)

    write_ndjson(out / "activity-logs" / "normal.ndjson", activity_normal)
    write_ndjson(out / "activity-logs" / "attacks.ndjson", activity_attack)
    write_ndjson(out / "nsg-flow-logs" / "normal.ndjson", nsg_normal)
    write_ndjson(out / "nsg-flow-logs" / "attacks.ndjson", nsg_attack)
    write_json(out / "attack-scenarios" / "named_attacks.json", catalog)
    write_json(
        out / "manifest.json",
        {
            "generated_at": iso(now),
            "subscription_id": args.subscription_id,
            "resource_group": args.resource_group,
            "counts": {
                "activity_normal": len(activity_normal),
                "activity_attack": len(activity_attack),
                "nsg_normal": len(nsg_normal),
                "nsg_attack": len(nsg_attack),
                "named_attack_scenarios": len(catalog),
            },
            "parser": "normalization.MultiCloudLogParser.parse_azure",
            "seed": args.seed,
        },
    )

    print(f"Generated Azure dummy telemetry under {out}")
    print(json.dumps({"manifest": str(out / "manifest.json"), **json.loads((out / "manifest.json").read_text())}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
