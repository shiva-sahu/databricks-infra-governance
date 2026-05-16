# databricks-governance-demo

> **"Escaping ClickOps" — Live Demo Repo**
> Azure Databricks · Terraform · GitHub Actions · Full IaC Governance

This repository is the live demo companion for the talk *"Escaping ClickOps: Maturing Databricks with Terraform, DABs, and GitHub Actions"*.

Every workspace, Unity Catalog object, permission, cluster policy, and secret scope in this platform is **declared in code, reviewed via PR, and enforced by automated governance tests**.

Nothing is created by clicking.

---

## Demo Story Arc

### Act 1 — Show the repo structure
> *"This is what a governed Databricks platform looks like as code."*

Walk the audience through:
- `terraform/modules/` — reusable building blocks
- `terraform/environments/` — per-environment composition
- `tests/governance/` — the rules the platform enforces on itself
- `.github/workflows/` — the CI/CD pipelines that run on every PR

### Act 2 — Open a bad PR
> *"Watch what happens when someone breaks a naming convention."*

Checkout the `demo/bad-pr` branch and open a PR to `dev`.
The governance tests will **fail in CI** — showing the audience exactly what gets caught and why.

```bash
git checkout demo/bad-pr
git push origin demo/bad-pr
# Open PR → base: dev → GitHub Actions triggers → governance tests fail
```

### Act 3 — Show drift detection catching a manual change
> *"Someone clicked. Here's how we find out."*

Trigger the drift detection workflow manually:
- GitHub → Actions → "Drift Detection" → Run workflow
- Show `terraform plan` output detecting unexpected changes
- Discuss: this runs on a cron schedule every 6 hours in production

### Act 4 — Merge the fix and watch it deploy
> *"Green CI. Clean governance. Deployed."*

Checkout `demo/good-pr`, open a PR, show all tests passing, merge, watch deploy-dev trigger.

---

## Repository Structure

```
databricks-governance-demo/
├── terraform/
│   ├── modules/
│   │   ├── workspace/          # Azure Databricks workspace + VNet
│   │   ├── unity-catalog/      # Metastore, catalogs, schemas, grants
│   │   ├── cluster-policy/     # Compute guardrails
│   │   ├── secret-scope/       # Secret scopes + ACLs
│   │   └── rbac/               # Group assignments + entitlements
│   └── environments/
│       ├── dev/                # Dev environment composition
│       └── prod/               # Prod environment composition
├── tests/
│   ├── governance/             # Naming, permissions, tagging rules
│   │   ├── test_naming.py
│   │   ├── test_permissions.py
│   │   ├── test_catalog_hierarchy.py
│   │   └── test_tagging.py
│   └── integration/            # Post-deploy smoke tests
│       └── test_workspace_health.py
├── scripts/
│   ├── drift_report.sh         # Generates drift report
│   └── validate_all.sh         # Full local validation
├── .github/
│   └── workflows/
│       ├── governance-check.yml    # Runs on every PR
│       ├── deploy.yml              # Deploys on merge
│       └── drift-detection.yml    # Runs on cron schedule
└── docs/
    └── GOVERNANCE.md           # The rules. Written down. Enforced.
```

---

## Governance Rules (enforced by CI)

| Rule | Test | Failure action |
|------|------|----------------|
| All resources tagged with `environment`, `team`, `cost_centre` | `test_tagging.py` | PR blocked |
| Catalog names follow `{env}_{team}_{domain}` pattern | `test_naming.py` | PR blocked |
| Schema names follow `{domain}_{layer}` (bronze/silver/gold) | `test_naming.py` | PR blocked |
| No `ALL PRIVILEGES` grants to individuals (groups only) | `test_permissions.py` | PR blocked |
| Production catalogs cannot be granted to `dev_team` group | `test_permissions.py` | PR blocked |
| Every catalog must have an owner defined | `test_catalog_hierarchy.py` | PR blocked |
| Cluster policies must define `autotermination_minutes` | `test_naming.py` | PR blocked |
| Secret scope names follow `{env}_{purpose}` pattern | `test_naming.py` | PR blocked |

---

## Quick Start

```bash
# 1. Clone
git clone https://github.com/YOUR_ORG/databricks-governance-demo
cd databricks-governance-demo

# 2. Install test dependencies
pip install pytest pyyaml python-hcl2 jsonschema

# 3. Run governance tests locally
pytest tests/governance/ -v

# 4. Validate Terraform
cd terraform/environments/dev
terraform init
terraform validate
terraform plan

# 5. Full validation script
./scripts/validate_all.sh
```

---

## Environment Variables (GitHub Secrets)

| Secret | Description |
|--------|-------------|
| `ARM_CLIENT_ID` | Azure SP Client ID |
| `ARM_CLIENT_SECRET` | Azure SP Secret |
| `ARM_SUBSCRIPTION_ID` | Azure Subscription |
| `ARM_TENANT_ID` | Azure AD Tenant |
| `DATABRICKS_HOST_DEV` | Dev workspace URL |
| `DATABRICKS_HOST_PROD` | Prod workspace URL |
| `DATABRICKS_TOKEN_DEV` | Dev SP token |
| `DATABRICKS_TOKEN_PROD` | Prod SP token |
| `TF_STATE_RESOURCE_GROUP` | Azure RG for TF state |
| `TF_STATE_STORAGE_ACCOUNT` | Azure Storage for TF state |
| `TF_STATE_CONTAINER` | Blob container for TF state |

---

## The Principle

> *"If it can't be reviewed in a pull request, it shouldn't exist in your platform."*
