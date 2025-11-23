# All your Postgres flexible servers (10 of them)
postgres_servers = {
  pg1 = {
    name               = "pg-alpha-01"
    resource_group_name = "rg-alpha-db"
    resource_id        = "/subscriptions/<alpha-eng-sbx-sub-id>/resourceGroups/rg-alpha-db/providers/Microsoft.DBforPostgreSQL/flexibleServers/pg-alpha-01"
  }
  pg2 = {
    name               = "pg-alpha-02"
    resource_group_name = "rg-alpha-db"
    resource_id        = "/subscriptions/<alpha-eng-sbx-sub-id>/resourceGroups/rg-alpha-db/providers/Microsoft.DBforPostgreSQL/flexibleServers/pg-alpha-02"
  }
  # ... add all remaining servers
}

alerts_location             = "East US"               # or your region
spoke_subscription_id       = "<alpha-eng-sbx-sub-id>"

# if hub / LAW in the same subscription, just reuse:
hub_subscription_id         = "<alpha-eng-sbx-sub-id>"
law_subscription_id         = "<alpha-eng-sbx-sub-id>"

log_analytics_workspace_rg  = "rg-observability"
log_analytics_workspace_id  = "law-alpha-eng-sbx"

action_groups = {
  email = {
    name               = "ag-email"
    resource_group_name = "rg-monitoring"
    subscription_id    = "<sub-id-that-has-email-ag>"
  }
  webhook = {
    name               = "ag-webhook"
    resource_group_name = "rg-monitoring"
    subscription_id    = "<sub-id-that-has-webhook-ag>"
  }
}