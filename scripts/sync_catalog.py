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
MINT_JSON = ROOT / "mint.json"

DEFAULT_SOURCE = "gs://tera-vllm-models/gateway-config.json"


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
    s = f"{per_mtok:.4f}".rstrip("0").rstrip(".")
    return f"${s}"


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

```bash
curl https://api.tera.gw/v1/chat/completions \\
  -H "Content-Type: application/json" \\
  -H "Authorization: Bearer $TERA_API_KEY" \\
  -d '{{
    "model": "{model_id}",
    "messages": [{{"role": "user", "content": "Hello"}}],
    "max_tokens": 64
  }}'
```
"""


def render_pricing(catalog: list[dict]) -> str:
    rows = []
    for e in catalog:
        p = e.get("pricing", {})
        rows.append(
            f"| `{e['id']}` | {fmt_price(p.get('prompt', '0'))} | "
            f"{fmt_price(p.get('completion', '0'))} | "
            f"`{e.get('quantization', '—')}` | "
            f"{e.get('context_length', '—'):,} |"
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

Reach out at [tom@hashbranch.com](mailto:tom@hashbranch.com) for committed-use pricing.
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
    for entry in catalog:
        slug = slugify(entry["id"])
        path = MODELS_DIR / f"{slug}.mdx"
        path.write_text(render_model_page(entry))
        written.append((entry["id"], slug, path))

    PRICING_PATH.write_text(render_pricing(catalog))

    print(f"wrote {len(written)} model pages and pricing.mdx")
    for model_id, slug, path in written:
        print(f"  {model_id} -> {path.relative_to(ROOT)}")

    expected_slugs = {f"models/{slug}" for _, slug, _ in written} | {"models/overview"}
    mint = json.loads(MINT_JSON.read_text())
    for group in mint.get("navigation", []):
        if group.get("group") == "Models":
            current = set(group["pages"])
            if expected_slugs != current:
                ordered = ["models/overview"] + sorted(s for s in expected_slugs if s != "models/overview")
                group["pages"] = ordered
                MINT_JSON.write_text(json.dumps(mint, indent=2) + "\n")
                print("updated mint.json navigation")
            break

    return 0


if __name__ == "__main__":
    sys.exit(main())
