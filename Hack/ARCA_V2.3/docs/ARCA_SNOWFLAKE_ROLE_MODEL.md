# Snowflake role model

ARCA's Snowflake fixtures follow a company-style custom role hierarchy. Snowflake's
default roles are used only for Snowflake infrastructure; every database, schema,
and object change goes through custom roles.

## When default roles are allowed

| Change type | Role to use |
|---|---|
| Users and roles (`CREATE/ALTER USER`, `CREATE ROLE`, `GRANT/REVOKE ROLE`) | `USERADMIN`, `SECURITYADMIN` |
| Warehouses and resource monitors | `SYSADMIN`, or the custom `WH_*` roles |
| Account-level settings (parameters, network policies, integrations, shares) | `ACCOUNTADMIN` |
| Anything on a database, schema, table, view, or an object privilege (`GRANT SELECT ...`), including `CREATE DATABASE` | Custom roles only |

The split is implemented in `backend/services/snowflake_roles.py`.

## Role layers

```
SYSADMIN
 └─ <APP>_FR  functional role, granted to users and service accounts
     ├─ DB_<DB>_RL            USAGE on the database
     ├─ DB_<DB>_C_RL          CREATE SCHEMA on the database (inherits DB_<DB>_RL)
     ├─ <DB>_<SCHEMA>_C_RL    CREATE TABLE/VIEW, owns the schema's managed tables
     │   └─ <DB>_<SCHEMA>_W_RL    INSERT/UPDATE/DELETE on the schema's tables
     │       └─ <DB>_<SCHEMA>_R_RL    USAGE on the schema, SELECT on its tables
     └─ WH_<WH>_O_RL          USAGE/OPERATE/MODIFY on the warehouse
         └─ WH_<WH>_U_RL          USAGE on the warehouse
```

Access roles (`_RL`) hold object privileges. Functional roles (`_FR`) hold no
privileges of their own; they inherit the access roles an app or team needs.
Every functional role rolls up to `SYSADMIN`, Snowflake's recommended pattern,
which is why `SYSADMIN` technically covers data changes but is still not allowed
to make them.

## Apps and their roles

| Functional role | Used by | Inherits |
|---|---|---|
| `FIN_REPORTING_APP_FR` | Finance reporting app | `DB_FINANCE_RL`, `FINANCE_REPORTING_R_RL`, `WH_REPORTING_U_RL` |
| `BI_DASHBOARD_APP_FR` | BI dashboards | `DB_MARKETING_RL`, `MARKETING_REPORTING_R_RL`, `WH_REPORTING_U_RL` (finance read is granted by change `CHG-SF-1007`) |
| `FIN_ETL_APP_FR` | Finance ETL | `DB_FINANCE_RL`, `FINANCE_STAGING_W_RL`, `FINANCE_REPORTING_W_RL`, `WH_REPORTING_U_RL` |
| `MKT_PIPELINE_APP_FR` | Marketing pipeline | `DB_MARKETING_RL`, `MARKETING_REPORTING_W_RL`, `WH_REPORTING_U_RL` |
| `DATA_ENG_FR` | Data engineering | `DB_DEV_RL`, `DEV_STAGING_C_RL`, `WH_REPORTING_U_RL` |
| `FIN_DDL_FR` | Finance deployments | `DB_FINANCE_C_RL`, `FINANCE_REPORTING_C_RL`, `FINANCE_STAGING_C_RL` |
| `MKT_DDL_FR` | Marketing deployments | `DB_MARKETING_C_RL`, `MARKETING_REPORTING_C_RL` |
| `REPORTING_OPS_FR` | Reporting operations | `WH_REPORTING_O_RL` |
| `PLATFORM_DB_ADMIN_FR` | Data platform team | `CREATE DATABASE` on the account (replaces `SYSADMIN` for database creation) |

## What ARCA checks

- **Access (A2):** a change that requests a default role for database or schema
  work is `OVERPRIVILEGED` and gets a `DEFAULT_ROLE_FOR_DATA_CHANGE` finding that
  names the narrowest custom role covering the change. If the default role also
  lacks the privileges, the result stays `INSUFFICIENT_PRIVILEGES` and the
  finding is still added.
- **Object grants:** `GRANT/REVOKE <privilege>` on an object needs `OWNERSHIP` of
  that object (or `MANAGE GRANTS`), so owners such as `FINANCE_STAGING_C_RL` can
  manage access to their own tables. `GRANT/REVOKE ROLE` still needs `MANAGE GRANTS`.
- **Execution (A3, A4):** a query that runs a database or schema change under a
  default role gets a `DEFAULT_ROLE_FOR_DATA_CHANGE` finding, in change and user
  investigations alike.
- **Ask ARCA (A5):** questions can name custom roles, for example
  "Investigate activities using FIN_DDL_FR in Snowflake in the last 30 days."

Scenarios `SF-UNIFIED-26` (`SYSADMIN` used to create a schema) and
`SF-UNIFIED-27` (`DB_FINANCE_C_RL` used for the same change) show the rule.
