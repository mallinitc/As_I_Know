variable "alerts_location" {
  description = "Location for alert resources (same region as your PostgreSQL flexible servers)."
  type        = string
}

variable "log_analytics_workspace_rg" {
  description = "Resource group of the Log Analytics workspace."
  type        = string
}

variable "log_analytics_workspace_id" {
  description = "Name of the Log Analytics workspace."
  type        = string
}

variable "spoke_subscription_id" {
  description = "Subscription ID where PostgreSQL flexible servers live (alpha-eng-sbx)."
  type        = string
}

variable "hub_subscription_id" {
  description = "Hub subscription ID (if not used, just set it equal to spoke_subscription_id)."
  type        = string
}

variable "law_subscription_id" {
  description = "Subscription ID where the Log Analytics workspace exists."
  type        = string
}

variable "action_groups" {
  description = <<EOF
Map describing the action groups used for alerts.
Expected keys: "email" and "webhook".
EOF
  type = map(object({
    name               = string
    resource_group_name = string
    subscription_id    = string
  }))
}

# --- New: all PostgreSQL flexible servers you want alerts on ----
variable "postgres_servers" {
  description = <<EOF
Map of PostgreSQL flexible servers to configure alerts for.

Example:
postgres_servers = {
  pg1 = {
    name               = "pg-flex-01"
    resource_group_name = "rg-db-alpha"
    resource_id        = "/subscriptions/.../resourceGroups/rg-db-alpha/providers/Microsoft.DBforPostgreSQL/flexibleServers/pg-flex-01"
  }
}
EOF
  type = map(object({
    name               = string
    resource_group_name = string
    resource_id        = string
  }))
}