#!/bin/bash
set -e

echo "🔧 Building full GitHub Pages site structure for toddwilliamsen.github.io"

# Create directories
mkdir -p articles
mkdir -p images

#############################################
# Create index.md (Advanced Homepage Layout)
#############################################
cat << 'EOT' > index.md
---
title: "Todd Williamsen"
layout: default
---

# 👋 Hi, I'm Todd Williamsen  
### Cloud Security Engineer • Azure Architecture • SOC Automation

I build secure-by-default cloud foundations, automate SOC workflows, and design Azure Landing Zone architectures that scale. This site is where I publish deep-dive technical articles, architecture diagrams, and cloud security breakdowns.

---

## 🚀 Featured Article  
### [Azure Landing Zone Security — A Technical Breakdown](articles/azure-landing-zone-security.md)

A detailed look at how identity, network segmentation, governance guardrails, and security operations are implemented inside Azure Landing Zones — with architecture diagrams.

---

## 📘 Technical Articles

- [Azure Landing Zone Security](articles/azure-landing-zone-security.md)

---

## 🧩 Architecture Diagrams

Visual breakdowns of cloud security patterns, Landing Zone structures, and SOC automation flows.

(See `/images/` folder for all diagrams.)

---

## 🛠️ What I Work On

- Azure Landing Zone architecture  
- Cloud security posture management  
- SOC automation (SOAR, playbooks, enrichment pipelines)  
- Identity-driven Zero Trust  
- Cloud-native detection engineering  
- Secure application patterns

---

## 📫 Connect With Me

- GitHub: https://github.com/toddwilliamsen  
- LinkedIn: Add your link here  
- Email: Add your contact here

---

## 📄 About This Site

This site is built using **GitHub Pages + Jekyll (minima theme)**.  
All content, diagrams, and articles are versioned in GitHub.
EOT

#############################################
# Create _config.yml (Theme + Settings)
#############################################
cat << 'EOT' > _config.yml
theme: minima
title: Todd Williamsen
description: Cloud Security Engineering • Azure Architecture • SOC Automation
markdown: kramdown
EOT

#############################################
# Create Azure Landing Zone Article
#############################################
cat << 'EOT' > articles/azure-landing-zone-security.md
# Azure Landing Zone Security: A Technical Breakdown

Azure Landing Zones implement security as a first-class architecture principle.  
Below is a technical walkthrough of how identity, network, governance, and security operations are structured inside a Landing Zone.

---

## 🔐 Identity & Access Architecture

Identity is the control plane. Everything inherits from it.

![Identity Architecture](../images/landing-zone-identity.png)

- Microsoft Entra ID as the global identity provider  
- Conditional Access enforcing device, location, and risk-based access  
- Privileged Identity Management (PIM) for JIT elevation  
- RBAC scoped at management groups  
- Identity-driven segmentation across platform, connectivity, and workload zones  

---

## 🌐 Network Security Architecture

Landing Zones enforce deterministic network behavior through segmentation + inspection.

![Network Architecture](../images/landing-zone-network.png)

- Hub-and-spoke or vWAN routing  
- Azure Firewall Premium for TLS inspection + IDPS  
- NSGs for subnet-level enforcement  
- ASGs for workload micro-segmentation  
- Private Endpoints to eliminate public exposure  
- VNet flow logs for traffic analytics  

---

## 📏 Governance & Compliance Architecture

Security posture is enforced through Azure-native governance.

![Governance Architecture](../images/landing-zone-governance.png)

- Management Groups define hierarchy  
- Azure Policy enforces encryption, diagnostics, allowed SKUs, network restrictions  
- Policy initiatives map to CAF + CIS  
- Blueprint-style deployment ensures repeatability  

---

## 🛡️ Security Operations Architecture

Landing Zones integrate Azure’s native security stack for detection and response.

![Security Operations Architecture](../images/landing-zone-security-ops.png)

- Defender for Cloud for CSPM + workload protection  
- Defender for Identity / Endpoint for hybrid threat detection  
- Azure Monitor + Log Analytics for telemetry  
- Sentinel for SIEM/SOAR + automation  

---

## 🏗️ Landing Zone Structural Architecture

A secure Landing Zone is modular and domain-driven.

![Landing Zone Structure](../images/landing-zone-structure.png)

- Platform Landing Zone  
- Connectivity Landing Zone  
- Application Landing Zones  

Each domain is isolated but governed under a consistent security baseline.

---

## Summary

Azure Landing Zones aren’t just a deployment pattern — they’re a full security architecture.  
Done correctly, they give you deterministic identity boundaries, segmented networks, enforced governance, and integrated security operations from day one.
EOT

#############################################
# Git Deployment
#############################################
echo "📡 Deploying to GitHub..."

git add .
git commit -m "Full site generation + article + homepage: $(date)"
git push origin main

echo "🚀 Deployment complete!"
echo "🌐 Your site is live at: https://toddwilliamsen.github.io"
