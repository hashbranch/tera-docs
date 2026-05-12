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

# Model ids whose .mdx is hand-maintained for partner/showcase content.
# Sync keeps them in pricing.mdx and docs.json (via parse_model_page) but
# never overwrites the page body.
SKIP_PAGE_REGEN = {
    "openai/gpt-oss-20b",
}


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
        with urllib.request.urlopen(source) as r:
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
    elif per_mtok == int(per_mtok):
        s = f"{int(per_mtok)}.00"
    else:
        s = f"{per_mtok:.2f}"
    return f"${s}"


PRICING_LINE_RE = re.compile(
    r"^\|\s*(?P<label>Input|Output)\s*\|\s*(?P<value>[^|]+?)\s*\|", re.MULTILINE
)
SPEC_LINE_RE = re.compile(
    r"^\|\s*\*\*(?P<key>[^*]+)\*\*\s*\|\s*(?P<value>[^|]+?)\s*\|", re.MULTILINE
)
MODEL_ID_RE = re.compile(r"Model id:\s*`([^`]+)`")


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

    quant = spec.get("Quantization", "—").strip("` ")
    return {
        "id": id_match.group(1),
        "context_length": context_length,
        "quantization": quant,
        "_display_prompt": prices.get("Input", "—").strip(),
        "_display_completion": prices.get("Output", "—").strip(),
        "_source": "disk",
    }


def display_pricing(entry: dict) -> tuple[str, str]:
    """Return (input, output) display strings for an entry, from either source."""
    if entry.get("_source") == "disk":
        return entry["_display_prompt"], entry["_display_completion"]
    p = entry.get("pricing", {})
    return fmt_price(p.get("prompt", "0")), fmt_price(p.get("completion", "0"))


def price_sort_key(display: str) -> float:
    if not display or display.lower() in ("free", "—"):
        return 0.0
    try:
        return float(display.replace("$", "").replace(",", ""))
    except ValueError:
        return 0.0


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
    entries.sort(key=lambda e: price_sort_key(display_pricing(e)[0]))
    return entries


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

    pricing_block = (
        f"| Input  | {fmt_price(pricing.get('prompt', '0'))} |\n"
        f"| Output | {fmt_price(pricing.get('completion', '0'))} |"
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
        example = f"""```bash
curl https://api.tera.gw/v1/chat/completions \\
  -H "Content-Type: application/json" \\
  -H "Authorization: Bearer $TERA_API_KEY" \\
  -d '{{
    "model": "{model_id}",
    "messages": [{{"role": "user", "content": "Hello"}}],
    "max_tokens": 256
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
| **HuggingFace** | [`{entry.get('hugging_face_id', model_id)}`](https://huggingface.co/{entry.get('hugging_face_id', model_id)}) |
| **Context length** | {entry.get('context_length', '—'):,} tokens |
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
    for e in models:
        in_p, out_p = display_pricing(e)
        ctx = e.get("context_length")
        ctx_display = f"{ctx:,}" if isinstance(ctx, int) else "—"
        rows.append(
            f"| `{e['id']}` | {in_p} | {out_p} | "
            f"`{e.get('quantization', '—')}` | {ctx_display} |"
        )
    table = "\n".join(rows)
    today = dt.date.today().isoformat()
    return f"""---
title: Pricing
description: "Per-token pricing for models on Tera."
---

All prices are in USD per **million tokens**. Updated {today}.

| Model | Input | Output | Quant | Context |
|---|---:|---:|---|---:|
{table}

Pricing is the same whether requests stream or not. Failed requests (5xx, 429) are not billed.

## How billing works

- **Input tokens** are counted from the rendered prompt after applying the model's chat template.
- **Output tokens** include generated text. For [reasoning models](/concepts/reasoning), `reasoning_content` tokens count toward output.
- **TTS** ([Kokoro](/models/kokoro-82m)) bills on input characters, surfaced as `prompt` token cost.

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
    skipped = []
    for entry in catalog:
        slug = slugify(entry["id"])
        path = MODELS_DIR / f"{slug}.mdx"
        if entry["id"] in SKIP_PAGE_REGEN and path.exists():
            skipped.append((entry["id"], slug, path))
            continue
        path.write_text(render_model_page(entry))
        written.append((entry["id"], slug, path))

    all_models = collect_all_models(catalog, MODELS_DIR)
    PRICING_PATH.write_text(render_pricing(all_models))

    print(f"wrote {len(written)} catalog model pages and pricing.mdx")
    for model_id, slug, path in written:
        print(f"  {model_id} -> {path.relative_to(ROOT)}")
    if skipped:
        print(f"skipped {len(skipped)} catalog pages (hand-maintained per SKIP_PAGE_REGEN):")
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
