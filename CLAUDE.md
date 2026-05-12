# CLAUDE.md — tera-docs

Mintlify docs for the Tera inference API. Lives at **docs.tera.gw**, auto-deployed on push to `main` via the Mintlify GitHub App.

## Architecture

- **Catalog source of truth**: `../tera/gateway/config.json` (or live `https://api.tera.gw/v1/models`).
- **Sync**: `scripts/sync_catalog.py` regenerates `models/*.mdx`, `pricing.mdx`, and the Models nav in `docs.json` from the catalog.
- **Hand-maintained pages** survive sync via two mechanisms:
  - **`SKIP_PAGE_REGEN`** (set in `scripts/sync_catalog.py`): catalog models whose page body is hand-curated. Pricing/nav still flow from the catalog. Currently: `openai/gpt-oss-20b`, `openai/gpt-oss-120b`.
  - **Disk-merge**: non-catalog model `.mdx` files (models not yet in `gateway/config.json`) are parsed for their pricing/spec rows by `parse_model_page` and folded into pricing.mdx and docs.json nav. Today: `Qwen/Qwen3.5-4B`, `openai/gpt-oss-120b`.
- **`pricing.mdx`** is fully generated. Never hand-edit — change the catalog or the source `.mdx` and re-run sync.
- **Pricing rows** are sorted by input price ascending. `fmt_price` always renders 2 decimal places (`$0.10`, never `$0.1`).

## Partner-grade model page template

Canonical reference: `models/gpt-oss-20b.mdx`. Built for downstream gateway/observability platforms (Respan-class) to register Tera as a routable provider with no surprises. Section order:

1. Frontmatter (title, descriptive tagline)
2. `<Info>` block with model id + OpenAI-SDK compatibility framing
3. **At a glance** table — model id, provider, HF link, context, max output, quantization, reasoning behavior, tool calling
4. **Pricing**
5. **Quickstart** — Python / Node / curl `<CodeGroup>` with a real prompt
6. **Reasoning** — non-streaming JSON + streaming SSE shapes; alias note if the model uses `reasoning_content`-style legacy field elsewhere
7. **Tool calling** — full multi-turn loop ending in a final answer
8. **Structured outputs / JSON mode** — both `json_object` and strict `json_schema`
9. **Streaming** — Python loop that handles reasoning + content deltas
10. **Sampling parameters** + **Supported features**
11. **OpenAI compatibility matrix** — ✅ / ➖ / ❌ per field
12. **Reliability and routing** — cold start, gateway retry, health-aware routing, concurrency, idempotency, streaming cancellation
13. **Observability** — `X-Tera-Request-ID` response header, `usage`, `finish_reason`, Python `with_raw_response` snippet
14. **Errors** — HTTP × `error.type` × retry guidance table
15. **Rate limits** — production-confident phrasing
16. **Cost example** — agentic-turn math at the model's rate
17. **Onboard** — concrete 4-step flow

To add a new partner-grade page: write the `.mdx`, add the model id to `SKIP_PAGE_REGEN`, run `python3 scripts/sync_catalog.py --source ../tera/gateway/config.json` to confirm pricing/nav update.

## Reasoning field naming

Different vLLM reasoning parsers emit different field names. Both are aliases.

| Parser | Models | Field emitted |
|---|---|---|
| `openai_gptoss` | `openai/gpt-oss-20b`, `openai/gpt-oss-120b` | `reasoning` |
| `qwen3` | `Qwen/Qwen3.5-*` | `reasoning_content` |

Docs follow OpenAI's spec recommendation (`reasoning`) for the gpt-oss family. `openapi.yaml` documents both fields with per-parser attribution so partners reading the spec see accurate per-model behavior. Don't conflate them — Qwen pages still say `reasoning_content` because that's what the qwen3 parser actually emits. Context: tera-docs issue #1.

## Forbidden phrases in public docs

Two grep gates **must come up empty** before pushing:

```bash
# No specific GPU SKUs (use generic "US-owned GPUs" if needed for positioning)
grep -rni -E "a100|h100|l4|sxm4|nvidia|80gb|24gb" . --include="*.mdx" --include="*.yaml" --include="*.json"

# Public docs assume production — never leak internal status
grep -rni -E "validation|candidate|spun up|spin up|on.demand|private beta|first integration|first partner|while we onboard|bring up capacity|provision additional|before turning up" . --include="*.mdx" --include="*.yaml"
```

The "US-owned GPUs" positioning line in `introduction.mdx` and `privacy.mdx` is intentional and kept.

Reasons: competitive (don't telegraph cost structure / hardware to competitors); supplier flexibility (Tera may switch hardware); confidence (partners reading the docs should never see hedge language that signals "this isn't real yet").

## Deploys

Mintlify auto-deploys on push to `main`. If a deploy is missed (GitHub App webhook occasionally drops a push event), redeploy manually from the Mintlify dashboard. Recurring misses → wire `mintlify deploy` into a GitHub Action.

Build status visible only to the Mintlify-app installer (`gh api repos/.../hooks` won't show GitHub Apps).

## Files

| Path | What |
|---|---|
| `docs.json` | Mintlify config — nav, branding, OpenAPI source. Nav Models group is partly sync-managed (see Architecture). |
| `openapi.yaml` | API spec; drives `/api-reference/*` playgrounds. Schema documents both `reasoning` and `reasoning_content` with per-parser attribution. |
| `favicon.png` | Dark `#111` tile with cream `#faf9f7` "T". Matches `tera-landing/src/app/favicon.ico`. |
| `models/*.mdx` | One per model. Auto-generated unless listed in `SKIP_PAGE_REGEN`. Canonical partner-grade example: `gpt-oss-20b.mdx`. |
| `concepts/*.mdx` | Reasoning, streaming, tool calling, OpenAI compatibility. Hand-maintained; Qwen-centric prose by design. |
| `api-reference/*.mdx` | Endpoint shims that reference `openapi.yaml`. |
| `scripts/sync_catalog.py` | Catalog → docs sync. Respects `SKIP_PAGE_REGEN`, merges disk-only models into pricing/nav. |
| `pricing.mdx` | Fully auto-generated. Sorted by input price ascending. |
| `introduction.mdx` `quickstart.mdx` `authentication.mdx` `privacy.mdx` | Hand-maintained narrative pages. |
| `README.md` | Human-facing: Mintlify dev, sync script usage. |
