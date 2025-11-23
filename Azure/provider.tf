terraform {
  required_version = ">= 1.5.0"

  required_providers {
    azurerm = {
      source  = "hashicorp/azurerm"
      version = "~> 3.111.0"
    }
  }
}

# Spoke subscription – this is where your PostgreSQL flexible servers live
provider "azurerm" {
  features {}
  alias                      = "spoke"
  subscription_id            = var.spoke_subscription_id
  skip_provider_registration = true
}

# Hub subscription (if you use it – keep or remove as per your existing setup)
provider "azurerm" {
  features {}
  alias                      = "hub"
  subscription_id            = var.hub_subscription_id
  skip_provider_registration = true
}

# Subscription containing Log Analytics workspace
provider "azurerm" {
  features {}
  alias                      = "law"
  subscription_id            = var.law_subscription_id
  skip_provider_registration = true
}

# Subscription that holds the *webhook* action group
provider "azurerm" {
  features {}
  alias                      = "monitoring"
  subscription_id            = var.action_groups["webhook"].subscription_id
  skip_provider_registration = true
}

# Subscription that holds the *email* action group
provider "azurerm" {
  features {}
  alias                      = "monitoring_email"
  subscription_id            = var.action_groups["email"].subscription_id
  skip_provider_registration = true
}