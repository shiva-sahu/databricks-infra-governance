# terraform/environments/prod/groups.tf
# ─────────────────────────────────────────────────────────────────────────────
# Azure AD groups used in this workspace.
# Groups are managed in Azure AD and synced here via SCIM provisioning.
# ─────────────────────────────────────────────────────────────────────────────

locals {
  groups = {
    data_engineers = "lll-data-engineers"
    data_analysts  = "lll-data-analysts"
  }
}
