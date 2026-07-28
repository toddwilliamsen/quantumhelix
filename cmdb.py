import logging

logger = logging.getLogger(__name__)

MOCK_CMDB = {
    "svc-shadow-0": {
        "owner": "Finance DevOps",
        "department": "Finance",
        "business_criticality": "Tier 1 (Mission Critical)",
        "asset_type": "Service Account",
        "description": "Production Billing Pipeline Automation"
    },
    "svc-shadow-1@corp.local": {
        "owner": "Data Platform",
        "department": "Engineering",
        "business_criticality": "Tier 2",
        "asset_type": "Application Identity",
        "description": "Nightly Data Lake Aggregation"
    },
    "compromised-azure-user-0@corp.local": {
        "owner": "T. Williamsen",
        "department": "Security Architecture",
        "business_criticality": "Tier 3",
        "asset_type": "User Account",
        "description": "Sandbox/Test Account"
    },
    "gcp-project.iam.gserviceaccount.com": {
        "owner": "Data Science",
        "department": "Analytics",
        "business_criticality": "Tier 2",
        "asset_type": "GCP Service Account",
        "description": "BigQuery Data Ingestion"
    }
}

def enrich_identity(identity_string):
    """
    Simulate a CMDB lookup.
    Prefers exact matches, then longest substring match to avoid
    ambiguous hits (e.g. svc-shadow-0 vs svc-shadow-01).
    """
    if not identity_string:
        return {
            "owner": "Unknown",
            "department": "Unknown",
            "business_criticality": "Unclassified",
            "asset_type": "Unknown",
            "description": "Asset not found in CMDB"
        }

    if identity_string in MOCK_CMDB:
        return MOCK_CMDB[identity_string]

    best_key = None
    for key in MOCK_CMDB:
        if key in identity_string and (best_key is None or len(key) > len(best_key)):
            best_key = key
    if best_key:
        return MOCK_CMDB[best_key]

    return {
        "owner": "Unknown",
        "department": "Unknown",
        "business_criticality": "Unclassified",
        "asset_type": "Unknown",
        "description": "Asset not found in CMDB"
    }
