########################
# Data sources
########################

data "azurerm_monitor_action_group" "email_ag" {
  name                = var.action_groups["email"].name
  resource_group_name = var.action_groups["email"].resource_group_name
  provider            = azurerm.monitoring_email
}

data "azurerm_monitor_action_group" "webhook_ag" {
  name                = var.action_groups["webhook"].name
  resource_group_name = var.action_groups["webhook"].resource_group_name
  provider            = azurerm.monitoring
}

data "azurerm_log_analytics_workspace" "law_workspace" {
  name                = var.log_analytics_workspace_id
  resource_group_name = var.log_analytics_workspace_rg
  provider            = azurerm.law
}

########################
# Locals – metrics & thresholds
########################

locals {
  # Postgres flexible server metrics
  # Reference: Microsoft.DBforPostgreSQL/flexibleServers metrics 0
  metrics = {
    cpu = {
      name  = "cpu_percent"
      agg   = "Average"
      title = "CPU percent"
    }
    storage = {
      name  = "storage_percent"
      agg   = "Average"
      title = "Storage percent"
    }
    failed_connections = {
      name  = "connections_failed"
      agg   = "Total"
      title = "Failed connections"
    }
  }

  # Alert levels (you can tune these)
  levels = {
    sev1 = {
      sev   = 1
      thr   = 90
      label = "critical"
    }
    sev2 = {
      sev   = 2
      thr   = 80
      label = "high"
    }
    sev3 = {
      sev   = 3
      thr   = 70
      label = "warning"
    }
  }

  # Build all metric-alert combinations: server x metric x level
  pg_metric_alerts = flatten([
    for server_key, server in var.postgres_servers : [
      for m_key, m in local.metrics : [
        for l_key, l in local.levels : {
          key         = "${server_key}-${m_key}-${l_key}"
          server_name = server.name
          server_rg   = server.resource_group_name
          server_id   = server.resource_id

          metric_name = m.name
          aggregation = m.agg
          severity    = l.sev
          threshold   = l.thr
          title       = "PG ${server.name} ${m.title} (${l.label})"
        }
      ]
    ]
  ])
}

########################
# Metric alerts (CPU, storage, failed connections)
########################

resource "azurerm_monitor_metric_alert" "pg_metric_alerts" {
  for_each = { for c in local.pg_metric_alerts : c.key => c }

  name                = each.value.title
  resource_group_name = each.value.server_rg
  scopes              = [each.value.server_id]
  description         = each.value.title
  severity            = each.value.severity
  enabled             = true
  window_size         = "PT5M"
  frequency           = "PT5M"

  criteria {
    metric_namespace = "Microsoft.DBforPostgreSQL/flexibleServers"
    metric_name      = each.value.metric_name
    aggregation      = each.value.aggregation
    operator         = "GreaterThan"
    threshold        = each.value.threshold
  }

  action {
    action_group_id = data.azurerm_monitor_action_group.email_ag.id
  }

  action {
    action_group_id = data.azurerm_monitor_action_group.webhook_ag.id
  }

  provider = azurerm.spoke
}

########################
# Diagnostic settings – send logs & metrics to Log Analytics
########################

resource "azurerm_monitor_diagnostic_setting" "pg_diagnostics" {
  for_each = var.postgres_servers

  name                       = "${each.value.name}-pg-diag"
  target_resource_id         = each.value.resource_id
  log_analytics_workspace_id = data.azurerm_log_analytics_workspace.law_workspace.id

  # PostgreSQLLogs -> goes to AzureDiagnostics table 1
  enabled_log {
    category = "PostgreSQLLogs"
  }

  # All metrics
  metric {
    category = "AllMetrics"
    enabled  = true
  }

  provider = azurerm.spoke
}

########################
# Scheduled query alerts (Log Analytics / KQL)
########################

# 1) Failed login / authentication issues
resource "azurerm_monitor_scheduled_query_rules_alert" "pg_failed_connections_alert" {
  for_each = var.postgres_servers

  name                = "${each.value.name}-pg-failed-connections-alert"
  resource_group_name = each.value.resource_group_name
  location            = var.alerts_location
  data_source_id      = data.azurerm_log_analytics_workspace.law_workspace.id
  severity            = 2
  enabled             = true
  frequency           = 5   # minutes
  time_window         = 5   # minutes
  description         = "Azure PostgreSQL failed connection attempts on ${each.value.name}"

  # Based on MS example for “unauthorized connections” on PostgreSQLLogs 2
  query = <<KQL
AzureDiagnostics
| where ResourceProvider == "MICROSOFT.DBFORPOSTGRESQL"
| where ResourceType == "FlexibleServers"
| where Category == "PostgreSQLLogs"
| where Resource == "${each.value.name}"
| where errorLevel_s == "FATAL"
| where Message matches regex "role.*does not exist"
    or Message matches regex "database.*does not exist"
    or Message contains "no pg_hba.conf"
    or Message contains "password authentication failed"
| summarize FailedConnections = count() by bin(TimeGenerated, 5m)
KQL

  trigger {
    operator  = "GreaterThan"
    threshold = 0
  }

  action {
    action_group = [
      data.azurerm_monitor_action_group.email_ag.id,
      data.azurerm_monitor_action_group.webhook_ag.id
    ]
  }

  provider = azurerm.spoke
}

# 2) Server restarts (acts like “offline/online” alert)
resource "azurerm_monitor_scheduled_query_rules_alert" "pg_server_restart_alert" {
  for_each = var.postgres_servers

  name                = "${each.value.name}-pg-server-restart-alert"
  resource_group_name = each.value.resource_group_name
  location            = var.alerts_location
  data_source_id      = data.azurerm_log_analytics_workspace.law_workspace.id
  severity            = 2
  enabled             = true
  frequency           = 5
  time_window         = 5
  description         = "Azure PostgreSQL server restart events on ${each.value.name}"

  # Based on MS “Server restarts” example for PostgreSQLLogs 3
  query = <<KQL
AzureDiagnostics
| where ResourceProvider == "MICROSOFT.DBFORPOSTGRESQL"
| where ResourceType == "FlexibleServers"
| where Category == "PostgreSQLLogs"
| where Resource == "${each.value.name}"
| where Message contains "database system was shut down at"
   or Message contains "database system is ready to accept"
| summarize RestartEvents = count() by bin(TimeGenerated, 5m)
KQL

  trigger {
    operator  = "GreaterThan"
    threshold = 0
  }

  action {
    action_group = [
      data.azurerm_monitor_action_group.email_ag.id,
      data.azurerm_monitor_action_group.webhook_ag.id
    ]
  }

  provider = azurerm.spoke
}