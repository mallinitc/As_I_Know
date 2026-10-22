# ARCA V2 Frontend

Enterprise frontend foundation for ARCA V2. This phase uses centralized synthetic demonstration data only and has no connection to the Python backend, cloud providers, databases, or LLM services.

## Run locally

```powershell
npm install
npm run dev -- --port 3000
```

The legacy ARCA V2 Streamlit application remains independent on port 8502.

## Validate

```powershell
npm run typecheck
npm run lint
npm run build
```
