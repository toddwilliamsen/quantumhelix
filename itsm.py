import os
import random
import logging
import requests

logger = logging.getLogger(__name__)

class ServiceNowClient:
    def __init__(self):
        self.url = os.environ.get("SERVICENOW_URL", "")
        self.user = os.environ.get("SERVICENOW_USER", "")
        self.password = os.environ.get("SERVICENOW_PASSWORD", "")
        
        self.is_mock = not bool(self.url)
        if self.is_mock:
            logger.info("ServiceNow integration running in MOCK mode (SERVICENOW_URL not set).")
        else:
            logger.info(f"ServiceNow integration connected to {self.url}")

    def create_incident(self, alert_id, identity, score, cmdb_context, details):
        """
        Creates an incident ticket in ServiceNow.
        Returns the Incident Number (e.g., INC001004).
        """
        short_description = f"🚨 Critical Quantum Threat Detected on {identity}"
        
        description = (
            f"Alert ID: {alert_id}\n"
            f"Threat Score: {score}\n"
            f"Identity: {identity}\n\n"
            f"CMDB Context:\n"
            f"- Owner: {cmdb_context.get('owner')}\n"
            f"- Criticality: {cmdb_context.get('business_criticality')}\n"
            f"- Asset Type: {cmdb_context.get('asset_type')}\n\n"
            f"Disagreement/Details:\n{details}"
        )
        
        payload = {
            "short_description": short_description,
            "description": description,
            "urgency": "1" if "Tier 1" in cmdb_context.get("business_criticality", "") else "2",
            "caller_id": "Quantum Helix Automated SecOps",
            "category": "Security"
        }

        if self.is_mock:
            inc_number = f"INC{random.randint(100000, 999999)}"
            logger.info(f"[MOCK ServiceNow] Incident Created: {inc_number} for {identity}")
            return inc_number
            
        else:
            try:
                # Actual API Call to ServiceNow Table API
                headers = {"Content-Type": "application/json", "Accept": "application/json"}
                response = requests.post(
                    f"{self.url}/api/now/table/incident", 
                    auth=(self.user, self.password), 
                    headers=headers,
                    json=payload,
                    timeout=5
                )
                response.raise_for_status()
                data = response.json()
                inc_number = data.get("result", {}).get("number", "INC_UNKNOWN")
                logger.info(f"ServiceNow Incident Created: {inc_number}")
                return inc_number
            except Exception as e:
                logger.error(f"Failed to create ServiceNow Incident: {e}")
                return None
