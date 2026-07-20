#!/usr/bin/env python3
"""Regenerate models/*.mdx and the pricing table from a Tera gateway catalog.

Usage:
    sync_catalog.py [--source gs://tera-vllm-models/gateway-config.json]
    sync_catalog.py --source ./local/config.json
    sync_catalog.py --source https://api.tera.gw/v1/models      # live
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import re
import subprocess
import sys
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
MODELS_DIR = ROOT / "models"
PRICING_PATH = ROOT / "pricing.mdx"
DOCS_JSON = ROOT / "docs.json"

DEFAULT_SOURCE = "gs://tera-vllm-models/gateway-config.json"

# Model ids whose .mdx body is hand-maintained for partner/showcase content.
# Sync DOES NOT overwrite the full page. Instead it surgically patches the
# content between sync marker comment pairs:
#
#   {/* sync:pricing:start */} … {/* sync:pricing:end */}
#   {/* sync:cost-example:start */} … {/* sync:cost-example:end */}
#
# If a SKIP_PAGE_REGEN page lacks the markers, sync falls back to the old
# behaviour (skip the page entirely) and prints a warning.
SKIP_PAGE_REGEN = {
    "openai/gpt-oss-20b",
    "openai/gpt-oss-120b",
}

# Fixed cost-example scenario used in partner pages.
# Row breakdown: 700 prompt in + 400 reasoning/tool out + 300 tool-result in + 200 final out
# Total: 1,000 input tokens, 600 output tokens per turn.
_CE_IN_PROMPT   = 700   # tokens
_CE_OUT_REASON  = 400   # tokens
_CE_IN_TOOL     = 300   # tokens
_CE_OUT_FINAL   = 200   # tokens
_CE_TURNS_DAY   = 50_000
_CE_DAYS_MONTH  = 30

HF_REPO_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*/[A-Za-z0-9][A-Za-z0-9._-]*$")


def slugify(model_id: str) -> str:
    base = model_id.split("/", 1)[1] if "/" in model_id else model_id
    base = base.lower()
    base = re.sub(r"\.", "-", base)
    base = re.sub(r"[^a-z0-9]+", "-", base)
    return base.strip("-")


def fetch(source: str) -> dict:
    if source.startswith("gs://"):
        out = subprocess.check_output(["gsutil", "cat", source])
        return json.loads(out)
    if source.startswith(("http://", "https://")):
        # Cloudflare in front of api.tera.gw 403s the default Python-urllib
        # user-agent, so send a normal one.
        req = urllib.request.Request(
            source,
            headers={"User-Agent": "tera-docs-sync/1.0 (+https://github.com/hashbranch/tera-docs)"},
        )
        with urllib.request.urlopen(req) as r:
            data = json.loads(r.read())
            if "catalog" in data:
                return data
            if data.get("object") == "list":
                return {"catalog": data["data"]}
            raise SystemExit(f"unexpected response shape from {source}")
    return json.loads(Path(source).read_text())


def fmt_price(price_per_token: str) -> str:
    try:
        v = float(price_per_token)
    except (TypeError, ValueError):
        return "—"
    if v == 0:
        return "Free"
    per_mtok = v * 1_000_000
    if per_mtok < 0.01:
        s = f"{per_mtok:.4f}".rstrip("0").rstrip(".") or "0"
    elif per_mtok < 1:
        s = f"{per_mtok:.4f}".rstrip("0").rstrip(".")
        if "." not in s:
            s = f"{s}.00"
        elif len(s.split(".", 1)[1]) == 1:
            s = f"{s}0"
    elif per_mtok == int(per_mtok):
        s = f"{int(per_mtok)}.00"
    else:
        s = f"{per_mtok:.2f}"
    return f"${s}"


PRICING_LINE_RE = re.compile(
    r"^\|\s*(?P<label>Input|Output|Cache Read)\s*\|\s*(?P<value>[^|]+?)\s*\|",
    re.MULTILINE,
)
SPEC_LINE_RE = re.compile(
    r"^\|\s*\*\*(?P<key>[^*]+)\*\*\s*\|\s*(?P<value>[^|]+?)\s*\|", re.MULTILINE
)
MODEL_ID_RE = re.compile(r"Model id:\s*`([^`]+)`")

# Marker patterns for surgical patching of SKIP_PAGE_REGEN pages.
_MARKER_RE = {
    "pricing": re.compile(
        r"(\{/\* sync:pricing:start \*/\}).*?(\{/\* sync:pricing:end \*/\})",
        re.DOTALL,
    ),
    "cost-example": re.compile(
        r"(\{/\* sync:cost-example:start \*/\}).*?(\{/\* sync:cost-example:end \*/\})",
        re.DOTALL,
    ),
}


def pricing_value(pricing: dict, key: str, legacy_key: str | None = None) -> str:
    """Return a pricing value from the current contract, with legacy fallback."""
    value = pricing.get(key)
    if value is None and legacy_key is not None:
        value = pricing.get(legacy_key)
    return str(value if value is not None else "0")


def is_nonzero_price(price_per_token: str) -> bool:
    try:
        return float(price_per_token) != 0
    except (TypeError, ValueError):
        return False


def is_zero_display_price(display: str) -> bool:
    value = display.strip()
    if not value or value == "—" or value.lower() == "free":
        return True
    try:
        return float(value.removeprefix("$").replace(",", "")) == 0
    except ValueError:
        return False


def render_pricing_block(in_price: str, out_price: str, cache_read_price: str | None = None) -> str:
    """Return the MDX content to place between sync:pricing markers (no markers included)."""
    cache_row = f"| Cache Read | {cache_read_price} |\n" if cache_read_price else ""
    return (
        f"\n\n| | per million tokens |\n"
        f"|---|---|\n"
        f"| Input  | {in_price} |\n"
        f"| Output | {out_price} |\n"
        f"{cache_row}\n"
    )


def render_cost_example_block(prompt_rate: float, completion_rate: float) -> str:
    """Return the MDX content to place between sync:cost-example markers.

    Uses the fixed scenario: 700 in + 400 out + 300 in / 200 out per turn,
    scaled to _CE_TURNS_DAY turns/day.
    """
    r1 = _CE_IN_PROMPT  * prompt_rate
    r2 = _CE_OUT_REASON * completion_rate
    r3 = _CE_IN_TOOL    * prompt_rate + _CE_OUT_FINAL * completion_rate
    per_turn = r1 + r2 + r3
    per_day  = per_turn * _CE_TURNS_DAY
    per_month = per_day * _CE_DAYS_MONTH

    total_in  = _CE_IN_PROMPT + _CE_IN_TOOL    # 1,000
    total_out = _CE_OUT_REASON + _CE_OUT_FINAL # 600

    return (
        f"\n\nTypical agentic turn with a tool call ({total_in:,} input tokens, {total_out:,} output tokens):\n\n"
        f"| Stage | Tokens | Cost |\n"
        f"|---|---:|---:|\n"
        f"| User prompt + system | {_CE_IN_PROMPT} in | ${r1:.7f} |\n"
        f"| Reasoning + tool call | {_CE_OUT_REASON} out | ${r2:.7f} |\n"
        f"| Tool result + final answer | {_CE_IN_TOOL} in / {_CE_OUT_FINAL} out | ${r3:.7f} |\n"
        f"| **Per turn** |  | **~${per_turn:.6f}** |\n\n"
        f"At {_CE_TURNS_DAY:,} turns/day this runs ~${per_day:.2f}/day "
        f"(~${per_month:.0f}/month). Volume committed-use pricing available "
        f"— email [hello@tera.gw](mailto:hello@tera.gw).\n\n"
    )


def patch_skip_page(path: Path, entry: dict) -> bool:
    """Patch sync-managed sections of a SKIP_PAGE_REGEN page.

    Returns True if the file was modified, False if unchanged or markers absent.
    """
    pricing = entry.get("pricing", {})
    input_rate_raw = pricing_value(pricing, "input", "prompt")
    output_rate_raw = pricing_value(pricing, "output", "completion")
    cache_read_raw = pricing_value(pricing, "cache_read")
    prompt_rate     = float(input_rate_raw)
    completion_rate = float(output_rate_raw)
    in_price  = fmt_price(input_rate_raw)
    out_price = fmt_price(output_rate_raw)
    cache_read_price = fmt_price(cache_read_raw) if is_nonzero_price(cache_read_raw) else None

    text = path.read_text()
    original = text

    # Patch pricing block
    if _MARKER_RE["pricing"].search(text):
        new_block = render_pricing_block(in_price, out_price, cache_read_price)
        text = _MARKER_RE["pricing"].sub(
            r"\g<1>" + new_block + r"\g<2>",
            text,
        )
    else:
        print(
            f"  warning: {path.name} has no sync:pricing markers — "
            "pricing section not patched",
            file=sys.stderr,
        )

    # Patch cost-example block
    if _MARKER_RE["cost-example"].search(text):
        new_block = render_cost_example_block(prompt_rate, completion_rate)
        text = _MARKER_RE["cost-example"].sub(
            r"\g<1>" + new_block + r"\g<2>",
            text,
        )
    else:
        print(
            f"  warning: {path.name} has no sync:cost-example markers — "
            "cost example not patched",
            file=sys.stderr,
        )

    if text != original:
        path.write_text(text)
        return True
    return False


def parse_model_page(path: Path) -> dict | None:
    """Extract id, spec, and pricing display strings from a hand-edited page.

    Used so model .mdx files that are not in the catalog still get rows
    in pricing.mdx and entries in docs.json without forcing them into
    gateway/config.json.
    """
    text = path.read_text()
    id_match = MODEL_ID_RE.search(text)
    if not id_match:
        return None
    spec = {m.group("key"): m.group("value") for m in SPEC_LINE_RE.finditer(text)}
    prices = {m.group("label"): m.group("value") for m in PRICING_LINE_RE.finditer(text)}

    ctx_raw = spec.get("Context length", "").replace(",", "").split()[0]
    try:
        context_length = int(ctx_raw)
    except ValueError:
        context_length = None

    quant_raw = spec.get("Quantization", "—")
    quant_match = re.search(r"`([^`]+)`", quant_raw)
    quant = quant_match.group(1) if quant_match else quant_raw.strip("` ")
    return {
        "id": id_match.group(1),
        "context_length": context_length,
        "quantization": quant,
        "_display_input": prices.get("Input", "—").strip(),
        "_display_output": prices.get("Output", "—").strip(),
        "_display_cache_read": prices.get("Cache Read", "—").strip(),
        "_source": "disk",
    }


def display_pricing(entry: dict) -> dict[str, str]:
    """Return display strings for public pricing fields, from either source."""
    if entry.get("_source") == "disk":
        cache_read = entry["_display_cache_read"]
        return {
            "input": entry["_display_input"],
            "output": entry["_display_output"],
            "cache_read": "—" if is_zero_display_price(cache_read) else cache_read,
        }
    p = entry.get("pricing", {})
    cache_read_raw = pricing_value(p, "cache_read")
    return {
        "input": fmt_price(pricing_value(p, "input", "prompt")),
        "output": fmt_price(pricing_value(p, "output", "completion")),
        "cache_read": fmt_price(cache_read_raw) if is_nonzero_price(cache_read_raw) else "—",
    }


def price_sort_key(display: str) -> float:
    if not display or display.lower() in ("free", "—"):
        return 0.0
    try:
        return float(display.replace("$", "").replace(",", ""))
    except ValueError:
        return 0.0


def is_huggingface_id(source: str) -> bool:
    """Return True for namespace/model Hugging Face repo ids."""
    return bool(HF_REPO_ID_RE.fullmatch(source))


def model_source_row(entry: dict) -> str:
    """Render a public source row only for web URLs or Hugging Face ids."""
    model_id = entry["id"]
    if "hugging_face_id" in entry and not entry["hugging_face_id"]:
        return ""
    source = str(entry.get("hugging_face_id") or model_id)
    if source.startswith(("http://", "https://")):
        return f"| **Source** | [`{source}`]({source}) |\n"
    if is_huggingface_id(source):
        return f"| **HuggingFace** | [`{source}`](https://huggingface.co/{source}) |\n"
    return ""


def collect_all_models(catalog: list[dict], models_dir: Path) -> list[dict]:
    """Catalog entries + any model .mdx files not in the catalog."""
    by_id: dict[str, dict] = {e["id"]: {**e, "_source": "catalog"} for e in catalog}
    if models_dir.is_dir():
        for path in sorted(models_dir.glob("*.mdx")):
            if path.stem == "overview":
                continue
            parsed = parse_model_page(path)
            if parsed and parsed["id"] not in by_id:
                by_id[parsed["id"]] = parsed
    entries = list(by_id.values())
    entries.sort(key=lambda e: price_sort_key(display_pricing(e)["input"]))
    return entries


def chat_token_limit_parameter(entry: dict) -> str:
    """Return the token-limit request field to show in chat examples."""
    params = set(entry.get("supported_sampling_parameters", []) or [])
    if "max_completion_tokens" in params and "max_tokens" not in params:
        return "max_completion_tokens"
    return "max_tokens"


def render_model_page(entry: dict) -> str:
    model_id = entry["id"]
    pricing = entry.get("pricing", {})
    features = entry.get("supported_features", []) or []
    params = entry.get("supported_sampling_parameters", []) or []
    inputs = entry.get("input_modalities", []) or []
    outputs = entry.get("output_modalities", []) or []

    feat_list = ", ".join(f"`{f}`" for f in features) if features else "—"
    param_list = ", ".join(f"`{p}`" for p in params) if params else "—"
    in_list = ", ".join(inputs) if inputs else "text"
    out_list = ", ".join(outputs) if outputs else "text"

    input_price_raw = pricing_value(pricing, "input", "prompt")
    output_price_raw = pricing_value(pricing, "output", "completion")
    cache_read_raw = pricing_value(pricing, "cache_read")
    cache_read_block = (
        f"\n| Cache Read | {fmt_price(cache_read_raw)} |"
        if is_nonzero_price(cache_read_raw)
        else ""
    )
    pricing_block = (
        f"| Input  | {fmt_price(input_price_raw)} |\n"
        f"| Output | {fmt_price(output_price_raw)} |"
        f"{cache_read_block}"
    )

    title = model_id.split("/", 1)[-1]
    description = f"{model_id} on Tera"

    is_tts = "audio" in outputs
    if is_tts:
        example = f"""```bash
curl https://api.tera.gw/v1/audio/speech \\
  -H "Content-Type: application/json" \\
  -H "Authorization: Bearer $TERA_API_KEY" \\
  -d '{{
    "model": "{model_id}",
    "input": "Hello from Tera.",
    "voice": "af_heart",
    "response_format": "wav",
    "speed": 1.0
  }}' \\
  --output speech.wav
```"""
    else:
        token_limit_param = chat_token_limit_parameter(entry)
        example = f"""```bash
curl https://api.tera.gw/v1/chat/completions \\
  -H "Content-Type: application/json" \\
  -H "Authorization: Bearer $TERA_API_KEY" \\
  -d '{{
    "model": "{model_id}",
    "messages": [{{"role": "user", "content": "Hello"}}],
    "{token_limit_param}": 256
  }}'
```"""

    return f"""---
title: "{title}"
description: "{description}"
---

<Info>
  Model id: `{model_id}` — pass this as the `model` field in API requests.
</Info>

## Spec

| | |
|---|---|
| **Provider** | {entry.get('owned_by', '—')} |
{model_source_row(entry)}| **Context length** | {entry.get('context_length', '—'):,} tokens |
| **Max output** | {entry.get('max_output_length', '—'):,} tokens |
| **Quantization** | `{entry.get('quantization', '—')}` |
| **Input modalities** | {in_list} |
| **Output modalities** | {out_list} |

## Pricing

| | per million tokens |
|---|---|
{pricing_block}

## Supported features

{feat_list}

## Sampling parameters

{param_list}

## Example

{example}
"""


def render_pricing(models: list[dict]) -> str:
    rows = []
    include_cache_read = any(display_pricing(e)["cache_read"] != "—" for e in models)
    for e in models:
        prices = display_pricing(e)
        ctx = e.get("context_length")
        ctx_display = f"{ctx:,}" if isinstance(ctx, int) else "—"
        cache_col = f" | {prices['cache_read']}" if include_cache_read else ""
        rows.append(
            f"| `{e['id']}` | {prices['input']} | {prices['output']}{cache_col} | "
            f"`{e.get('quantization', '—')}` | {ctx_display} |"
        )
    table = "\n".join(rows)
    today = dt.date.today().isoformat()
    cache_heading = " | Cache Read" if include_cache_read else ""
    cache_separator = "|---:" if include_cache_read else ""
    return f"""---
title: Pricing
description: "Per-token pricing for models on Tera."
---

All prices are in USD per **million tokens**. Updated {today}.

| Model | Input | Output{cache_heading} | Quant | Context |
|---|---:|---:{cache_separator}|---|---:|
{table}

Pricing is the same whether requests stream or not. Failed requests (5xx, 429) are not billed.

## How billing works

- **Input tokens** are counted from the rendered prompt after applying the model's chat template.
- **Output tokens** include generated text. For [reasoning models](/concepts/reasoning), `reasoning_content` tokens count toward output.
- **Cache read tokens** are cached input tokens reported by the backend. They appear in pricing only for models with non-zero cache-read rates.

## Volume discounts

Reach out at [hello@tera.gw](mailto:hello@tera.gw) for committed-use pricing.
"""


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", default=DEFAULT_SOURCE)
    args = parser.parse_args()

    config = fetch(args.source)
    catalog = config.get("catalog") or config.get("data") or []
    if not catalog:
        print(f"no catalog entries found in {args.source}", file=sys.stderr)
        return 1

    MODELS_DIR.mkdir(parents=True, exist_ok=True)

    written = []
    patched = []
    skipped = []
    for entry in catalog:
        slug = slugify(entry["id"])
        path = MODELS_DIR / f"{slug}.mdx"
        if entry["id"] in SKIP_PAGE_REGEN and path.exists():
            changed = patch_skip_page(path, entry)
            if changed:
                patched.append((entry["id"], slug, path))
            else:
                skipped.append((entry["id"], slug, path))
            continue
        path.write_text(render_model_page(entry))
        written.append((entry["id"], slug, path))

    all_models = collect_all_models(catalog, MODELS_DIR)
    PRICING_PATH.write_text(render_pricing(all_models))

    print(f"wrote {len(written)} catalog model pages and pricing.mdx")
    for model_id, slug, path in written:
        print(f"  {model_id} -> {path.relative_to(ROOT)}")
    if patched:
        print(f"patched {len(patched)} SKIP_PAGE_REGEN pages (pricing + cost example updated):")
        for model_id, _, path in patched:
            print(f"  {model_id} -> {path.relative_to(ROOT)}")
    if skipped:
        print(f"no-op {len(skipped)} SKIP_PAGE_REGEN pages (already current):")
        for model_id, _, path in skipped:
            print(f"  {model_id} -> {path.relative_to(ROOT)}")
    disk_only = [e for e in all_models if e.get("_source") == "disk"]
    if disk_only:
        print(f"preserved {len(disk_only)} hand-maintained model pages in pricing.mdx:")
        for e in disk_only:
            print(f"  {e['id']}")

    expected_slugs = {f"models/{slugify(e['id'])}" for e in all_models} | {"models/overview"}
    docs = json.loads(DOCS_JSON.read_text())
    nav = docs.get("navigation", {})
    containers = (
        nav.get("anchors", [])
        + nav.get("tabs", [])
        + nav.get("dropdowns", [])
    )
    updated = False
    for container in containers:
        for group in container.get("groups", []):
            if group.get("group") == "Models":
                current = set(group.get("pages", []))
                if expected_slugs != current:
                    ordered = ["models/overview"] + sorted(s for s in expected_slugs if s != "models/overview")
                    group["pages"] = ordered
                    updated = True
                break
    if updated:
        DOCS_JSON.write_text(json.dumps(docs, indent=2) + "\n")
        print("updated docs.json navigation")

    return 0


if __name__ == "__main__":
    sys.exit(main())
