# docs/GOVERNANCE.md

# Databricks Platform Governance Rules

> This document is the source of truth for all governance rules enforced by this repository.
> Every rule here has a corresponding automated test in `tests/governance/`.
> Rules are not suggestions. They are enforced by CI on every PR.

---

## Principle

**If it can't be reviewed in a pull request, it shouldn't exist in your platform.**

Every workspace, catalog, schema, cluster policy, secret scope, and permission in this platform was:
1. Declared in code
2. Reviewed by a peer via PR
3. Validated by automated governance tests
4. Deployed by CI/CD — never by hand

---

## Naming Conventions

### Catalogs
**Pattern:** `{env}_{team}_{domain}`

| Component | Rules |
|-----------|-------|
| `env` | Must be `dev`, `staging`, or `prod` |
| `team` | Lowercase, underscores, max 20 chars |
| `domain` | Business domain. Lowercase, underscores, max 20 chars |

**Valid:** `dev_ecommerce_orders`, `prod_finance_gl`, `staging_platform_shared`
**Invalid:** `EcommerceData`, `orders`, `dev-ecommerce`, `DEV_ECOMMERCE_ORDERS`

**Test:** `tests/governance/test_naming.py::TestCatalogNaming`

---

### Schemas (Medallion Architecture)
**Pattern:** `{domain}_{layer}`

| Layer | Purpose | Who writes | Who reads |
|-------|---------|------------|-----------|
| `bronze` | Raw ingested data, unmodified | Engineers | Engineers |
| `silver` | Cleansed, validated, joined | Engineers | Engineers + Analysts |
| `gold` | Business-ready, aggregated | Engineers | Analysts + Scientists + BI tools |

**Valid:** `orders_bronze`, `customers_silver`, `revenue_gold`
**Invalid:** `orders_raw`, `customers_processed`, `revenue_presentation`, `orders_landing`

**Test:** `tests/governance/test_naming.py::TestSchemaNaming`

---

### Secret Scopes
**Pattern:** `{env}_{purpose}`

**Valid:** `dev_postgres`, `prod_api_keys`, `staging_service_bus`
**Invalid:** `postgres`, `DEV_POSTGRES`, `dev-postgres`

**Test:** `tests/governance/test_naming.py::TestSecretScopeNaming`

---

### Cluster Policies
**Pattern:** `{env}_{purpose}`

**Valid:** `dev_standard_interactive`, `prod_job_cluster`
**Invalid:** `interactive`, `my_policy`, `PROD-JOB`

**Test:** `tests/governance/test_naming.py::TestClusterPolicyNaming`

---

### Azure Resource Groups
**Pattern:** `{prefix}-{env}-{purpose}-rg`

**Valid:** `gcw-dev-databricks-rg`, `demo-prod-analytics-rg`
**Invalid:** `databricks-rg`, `dev_databricks`, `DatabricksRG`

---

## Permission Rules

### Forbidden Patterns

| Pattern | Why forbidden | Alternative |
|---------|---------------|-------------|
| `ALL PRIVILEGES` | Grants DROP, MANAGE GRANTS, future privileges. Eliminates audit clarity. | Use explicit list: `["USE_CATALOG", "SELECT", "MODIFY"]` |
| `MANAGE GRANTS` to non-admins | Allows privilege escalation — granted principal can grant any privilege | Only `dbx-admins`, `platform_engineers`, `dba_team` may hold MANAGE GRANTS |
| Individual user grants | Breaks at team changes, invisible to access reviews, unscalable | Add user to an Azure AD group. Grant to the group. |
| `dev_team` write access in prod | Dev team may read prod data for debugging; never write | Use `SELECT`, `USE_CATALOG`, `USE_SCHEMA` only in prod for dev_team |
| Analyst groups with write privileges | Analysts are consumers, not producers | `data_analysts`, `finance_analysts` etc. get `SELECT`, `USE_*` only |

**Test:** `tests/governance/test_permissions.py`

---

### Permission Hierarchy

```
Account Admin (Databricks Account Console)
  └── Workspace Admin  [dbx-admins, platform_engineers]
        ├── Data Engineer  [data_engineers, {domain}_data_engineers]
        │     └── Can create clusters, tables, schemas
        ├── Data Analyst   [{domain}_analysts, data_analysts]
        │     └── Read-only: SELECT, USE_CATALOG, USE_SCHEMA
        ├── Data Scientist [data_scientists]
        │     └── SELECT + can create clusters for ML workloads
        └── Service Principal [pipeline_sp, ci_sp]
              └── Minimum privileges needed for their specific job
```

---

## Tagging Requirements

All Azure resources **must** include these tags:

| Tag | Format | Example |
|-----|--------|---------|
| `environment` | `dev` \| `staging` \| `prod` | `dev` |
| `team` | lowercase string | `ecommerce` |
| `cost_centre` | `CC-XXXX` (4 digits) | `CC-1002` |
| `managed_by` | always `terraform` | `terraform` |

Use `local.common_tags` in every module — it enforces these automatically.

**Test:** `tests/governance/test_tagging.py`

---

## Cluster Policy Requirements

Every cluster policy must:

1. **Set `autotermination_minutes`** — no eternal clusters
   - Interactive: max 120 min (dev), 60 min (prod)
   - Job: max 30 min after job completion

2. **Restrict to approved runtimes** — approved Databricks LTS versions only

3. **Enforce team + cost_centre tags** — for cost attribution

4. **Set `data_security_mode`** — `USER_ISOLATION` for interactive, `SINGLE_USER` for jobs

5. **Cap node counts** — interactive max 4 (dev) / 10 (prod); jobs max 8 (dev) / 20 (prod)

---

## Catalog Completeness Requirements

Every catalog must have:
- An `owner` (a group, never an individual)
- A human-readable `comment` (minimum 10 characters)
- A `cost_centre` property in CC-XXXX format
- All three medallion schemas: `bronze`, `silver`, `gold`
- `lifecycle { prevent_destroy = true }` in production

---

## Drift Policy

If `terraform plan` shows changes that were not deployed by CI/CD, **drift has occurred**.

Drift = someone made a manual change. This is a governance violation.

**Response procedure:**
1. A GitHub issue is automatically created with the full drift report
2. The owning team has **48 hours** to resolve drift
3. Resolution options:
   - Run `terraform apply` to revert (preferred)
   - Codify the change via PR if it was intentional
4. Unresolved drift after 48h escalates to platform engineering

Drift detection runs every 6 hours via `.github/workflows/drift-detection.yml`.

---

## Adding a New Catalog

To add a new catalog, open a PR modifying `terraform/environments/{env}/main.tf`:

```hcl
module "unity_catalog" {
  # ... existing config ...
  
  catalogs = {
    # ADD YOUR CATALOG HERE:
    my_new_domain = {
      team        = "my_team"          # Your team identifier
      domain      = "my_domain"        # Business domain
      comment     = "Description of what this catalog contains and who uses it."
      owner_group = "my_team_engineers"  # A group, not an individual
      cost_centre = "CC-XXXX"          # Your cost centre code
      grants = [
        {
          principal  = "my_team_engineers"
          privileges = ["USE_CATALOG", "CREATE_SCHEMA", "CREATE_TABLE", "MODIFY"]
        },
        {
          principal  = "data_analysts"
          privileges = ["USE_CATALOG", "SELECT"]
        }
      ]
      schema_grants = {
        bronze = [{ principal = "my_team_engineers", privileges = ["USE_SCHEMA", "CREATE_TABLE", "MODIFY", "SELECT"] }]
        silver = [{ principal = "my_team_engineers", privileges = ["USE_SCHEMA", "CREATE_TABLE", "MODIFY", "SELECT"] },
                  { principal = "data_analysts",     privileges = ["USE_SCHEMA", "SELECT"] }]
        gold   = [{ principal = "my_team_engineers", privileges = ["USE_SCHEMA", "CREATE_TABLE", "MODIFY", "SELECT"] },
                  { principal = "data_analysts",     privileges = ["USE_SCHEMA", "SELECT"] }]
      }
    }
  }
}
```

The PR will trigger governance tests automatically. Fix any failures before requesting review.
