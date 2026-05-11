# tera-docs

Public documentation for the [Tera API](https://api.tera.gw) — an OpenAI-compatible inference gateway. Lives at **docs.tera.gw**, deployed via [Mintlify](https://mintlify.com).

## Local preview

```bash
npm i -g mintlify
mintlify dev
```

Opens at http://localhost:3000 with hot reload.

## Structure

```
docs.json            # Mintlify config (nav, branding, OpenAPI source)
openapi.yaml         # API spec — drives /api-reference/* playgrounds
introduction.mdx
quickstart.mdx
authentication.mdx
pricing.mdx          # auto-generated from gateway catalog
concepts/            # streaming, reasoning, tool-calling, openai-compat
api-reference/       # one MDX shim per endpoint, references openapi.yaml
models/              # per-model pages, auto-generated
scripts/sync_catalog.py  # regenerates models/*.mdx + pricing.mdx from /v1/models
```

## Updating model pages

`models/*.mdx` and `pricing.mdx` are generated from the live Tera catalog. Do **not** hand-edit them — re-run the sync script:

```bash
# From the live API
python3 scripts/sync_catalog.py --source https://api.tera.gw/v1/models

# From the GCS source-of-truth
python3 scripts/sync_catalog.py --source gs://tera-vllm-models/gateway-config.json

# From a local file (useful for testing)
python3 scripts/sync_catalog.py --source ../tera/gateway/config.json
```

A daily GitHub Action (`.github/workflows/sync-catalog.yml`) runs the same command against the live API and opens a PR when anything changed.

## Editing other content

Everything in `concepts/`, `introduction.mdx`, `quickstart.mdx`, `authentication.mdx`, and the `api-reference/*.mdx` shims are hand-maintained. The `openapi.yaml` spec is the source of truth for request/response shapes — edit there to update playgrounds across the API reference.

## Deploys

Mintlify auto-deploys on push to `main`. PRs get preview deploys at `<branch>.docs.mintlify.app`.

## Domain

CNAME `docs.tera.gw` → Mintlify (proxied off through Cloudflare; Mintlify handles TLS).
