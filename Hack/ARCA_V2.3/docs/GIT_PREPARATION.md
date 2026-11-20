# Manual Git Preparation

The version folders intentionally contain no nested `.git` directories. From the existing parent repository, review the snapshots before staging them:

```powershell
git status --short
git check-ignore -v ARCA_V1/.env.example ARCA_V1/data/aws/changes.json ARCA_V1/data/azure/servicenow_changes.json ARCA_V1/data/snowflake/changes.json
git add ARCA_V1 ARCA_V2
git status --short
```

Do not stage `.env`, `.venv`, logs, generated outputs, keys, credential files, or `archives/ARCA_V1.zip`. Review `git diff --cached` before creating any manual commit. No commit or push is performed by the snapshot process.
