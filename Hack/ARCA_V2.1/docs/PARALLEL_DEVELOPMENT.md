# ARCA V2.1 parallel development

`main` is the reviewed integration branch. Development starts from `feature/azure` for Developer 1 and `feature/snowflake` for Developer 2. After the initial repository setup, changes reach `main` only through reviewed pull requests; pull requests are never merged automatically.

## Ownership boundaries

- Azure: `backend/api/routes/azure.py`, `backend/schemas/azure.py`, `backend/repositories/azure.py`, `backend/services/azure_*`, `data/azure/`, and Azure-focused tests.
- Snowflake: `backend/api/routes/snowflake.py`, `backend/schemas/snowflake.py`, `backend/repositories/snowflake.py`, `backend/services/snowflake*`, `data/snowflake/`, and Snowflake-focused tests.
- AWS: frozen unless a reviewed cross-provider compatibility fix is explicitly approved.
- Shared contracts: `backend/main.py`, provider registration, common schemas, analytics, investigations, Ask ARCA, shared frontend types/API clients, and dependency manifests require review from both developers.

Provider work must preserve existing versioned routes and response fields. Each pull request should run its provider-focused tests plus shared API-contract tests. Changes to shared code require AWS, Azure, and Snowflake regression checks.

## CODEOWNERS

The repository structure supports provider-specific CODEOWNERS rules, but GitHub usernames or team slugs for Developer 1 and Developer 2 are not stored in the project. Add `.github/CODEOWNERS` after those identities are confirmed; do not use unverifiable placeholder accounts.
