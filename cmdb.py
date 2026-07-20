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
    Matches the normalized identity string against the mock CMDB.
    """
    for key, data in MOCK_CMDB.items():
        if key in identity_string:
            return data
    
    return {
        "owner": "Unknown",
        "department": "Unknown",
        "business_criticality": "Unclassified",
        "asset_type": "Unknown",
        "description": "Asset not found in CMDB"
    }
