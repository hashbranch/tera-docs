# CLAUDE.md — tera-docs

Mintlify docs for the Tera inference API. Lives at **docs.tera.gw**, auto-deployed on push to `main` via the Mintlify GitHub App.

## Architecture

- **Catalog source of truth**: `../tera/gateway/config.json` (or live `https://api.tera.gw/v1/models`).
- **Sync**: `scripts/sync_catalog.py` regenerates `models/*.mdx`, `pricing.mdx`, and the Models nav in `docs.json` from the catalog.
- **Hand-maintained pages** survive sync via two mechanisms:
  - **`SKIP_PAGE_REGEN`** (set in `scripts/sync_catalog.py`): catalog models whose page body is hand-curated. Sync patches only the content between sync marker comments (see below) and leaves all prose, code, and narrative untouched. Currently: `openai/gpt-oss-20b`, `openai/gpt-oss-120b`.
  - **Disk-merge**: non-catalog model `.mdx` files (models not yet in `gateway/config.json`) are parsed for their pricing/spec rows by `parse_model_page` and folded into pricing.mdx and docs.json nav.
- **`pricing.mdx`** is fully generated. Never hand-edit — change the catalog or the source `.mdx` and re-run sync.
- **Pricing rows** are sorted by input price ascending. `fmt_price` always renders 2 decimal places (`$0.10`, never `$0.1`).

## Auto-sync workflow

`.github/workflows/sync-catalog.yml` runs daily at **08:00 UTC** (cron `0 8 * * *`) and on `workflow_dispatch`.

Pipeline:
1. Checks out the repo with write permission.
2. Runs `python3 scripts/sync_catalog.py --source https://api.tera.gw/v1/models`.
3. Runs both forbidden-phrase grep gates (see below). If either gate fires, the job **fails immediately** and nothing is committed — the failed run is the alert.
4. If gates pass and `git diff` shows changes under `models/`, `pricing.mdx`, or `docs.json`: commits straight to `main` with author `tera-sync-bot` and message `chore: auto-sync catalog from live API [skip ci]`. The `[skip ci]` tag prevents a deploy loop.
5. If a commit was made: opens a GitHub issue summarising added models, removed models, and updated files so Tom sees it after the fact. Issue is only created when something actually changed — no noise on no-op runs.
6. Always writes a job summary to `$GITHUB_STEP_SUMMARY` (visible in the Actions tab).

To trigger manually: Actions → "Sync model catalog" → "Run workflow".

## Sync marker mechanism for SKIP_PAGE_REGEN pages

Partner-grade pages in `SKIP_PAGE_REGEN` contain two pairs of MDX comment markers that delimit machine-managed regions:

```
{/* sync:pricing:start */}
… pricing table (auto-updated) …
{/* sync:pricing:end */}

{/* sync:cost-example:start */}
… cost-example block (auto-updated) …
{/* sync:cost-example:end */}
```

During sync, the script replaces content between each marker pair with values computed from the live catalog — the pricing table from `pricing.prompt`/`pricing.completion`, and the cost-example figures from those rates using the fixed scenario: **50,000 turns/day, 1,000 input tokens + 600 output tokens per turn** (staged as 700 in prompt + 400 out reasoning/tool call + 300 in tool result + 200 out final answer).

Everything outside the markers is preserved byte-for-byte. If a SKIP_PAGE_REGEN page lacks the markers, sync falls back to the old behaviour (skip entirely) and prints a warning — it does not error.

**To add a new partner-grade page:**
1. Write the `.mdx` with the full partner-grade template.
2. Place `{/* sync:pricing:start */}` / `{/* sync:pricing:end */}` around the pricing table, and `{/* sync:cost-example:start */}` / `{/* sync:cost-example:end */}` around the cost-example block.
3. Add the model id to `SKIP_PAGE_REGEN` in `scripts/sync_catalog.py`.
4. Run `python3 scripts/sync_catalog.py --source https://api.tera.gw/v1/models` to confirm pricing/nav update and that the marker patch is a no-op on the initial values.

## Partner-grade model page template

Canonical reference: `models/gpt-oss-20b.mdx`. Built for downstream gateway/observability platforms (Respan-class) to register Tera as a routable provider with no surprises. Section order:

1. Frontmatter (title, descriptive tagline)
2. `<Info>` block with model id + OpenAI-SDK compatibility framing
3. **At a glance** table — model id, provider, HF link, context, max output, quantization, reasoning behavior, tool calling
4. **Pricing** — table wrapped in `sync:pricing` markers
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
16. **Cost example** — agentic-turn math at the model's rate, wrapped in `sync:cost-example` markers
17. **Onboard** — concrete 4-step flow

## Reasoning field naming

Different vLLM reasoning parsers emit different field names. Both are aliases.

| Parser | Models | Field emitted |
|---|---|---|
| `openai_gptoss` | `openai/gpt-oss-20b`, `openai/gpt-oss-120b` | `reasoning` |
| `qwen3` | `Qwen/Qwen3.5-*` | `reasoning_content` |

Docs follow OpenAI's spec recommendation (`reasoning`) for the gpt-oss family. `openapi.yaml` documents both fields with per-parser attribution so partners reading the spec see accurate per-model behavior. Don't conflate them — Qwen pages still say `reasoning_content` because that's what the qwen3 parser actually emits. Context: tera-docs issue #1.

## Forbidden phrases in public docs

Two grep gates **must come up empty** before pushing. The CI workflow enforces these automatically; failing gates block the auto-commit.

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
| `docs.json` | Mintlify config — nav, branding, OpenAPI source. Nav Models group is sync-managed (see Architecture). |
| `openapi.yaml` | API spec; drives `/api-reference/*` playgrounds. Schema documents both `reasoning` and `reasoning_content` with per-parser attribution. |
| `favicon.png` | Dark `#111` tile with cream `#faf9f7` "T". Matches `tera-landing/src/app/favicon.ico`. |
| `models/*.mdx` | One per model. Auto-generated unless listed in `SKIP_PAGE_REGEN`. Canonical partner-grade example: `gpt-oss-20b.mdx`. |
| `concepts/*.mdx` | Reasoning, streaming, tool calling, OpenAI compatibility. Hand-maintained; Qwen-centric prose by design. |
| `api-reference/*.mdx` | Endpoint shims that reference `openapi.yaml`. |
| `scripts/sync_catalog.py` | Catalog → docs sync. Patches `SKIP_PAGE_REGEN` pages between sync markers; merges disk-only models into pricing/nav. |
| `pricing.mdx` | Fully auto-generated. Sorted by input price ascending. |
| `.github/workflows/sync-catalog.yml` | Daily auto-sync at 08:00 UTC. Grep gates guard the commit; issues notify on change. |
| `introduction.mdx` `quickstart.mdx` `authentication.mdx` `privacy.mdx` | Hand-maintained narrative pages. |
| `README.md` | Human-facing: Mintlify dev, sync script usage. |

<!-- Tera shared context — auto-loaded from ../tera-context (the shared brain). Keep it pulled. -->
@../tera-context/OVERVIEW.md
@../tera-context/projects/docs.md
@../tera-context/CHANGELOG.md
