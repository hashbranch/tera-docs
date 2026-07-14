from __future__ import annotations

import importlib.util
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("sync_catalog", ROOT / "scripts" / "sync_catalog.py")
assert SPEC is not None
sync_catalog = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(sync_catalog)


def test_display_pricing_reads_new_contract_keys():
    entry = {
        "pricing": {
            "input": "0.00000154",
            "output": "0.00000484",
            "cache_read": "0.000000286",
        }
    }

    assert sync_catalog.display_pricing(entry) == {
        "input": "$1.54",
        "output": "$4.84",
        "cache_read": "$0.286",
    }


def test_display_pricing_keeps_legacy_fallback_until_api_rolls_forward():
    entry = {
        "pricing": {
            "prompt": "0.0000006",
            "completion": "0.0000017",
        }
    }

    assert sync_catalog.display_pricing(entry) == {
        "input": "$0.60",
        "output": "$1.70",
        "cache_read": "—",
    }


def test_model_page_omits_zero_cache_read_row():
    page = sync_catalog.render_model_page(
        {
            "id": "test/zero-cache",
            "context_length": 1000,
            "max_output_length": 100,
            "pricing": {
                "input": "0.0000006",
                "output": "0.0000017",
                "cache_read": "0",
            },
        }
    )

    assert "| Input  | $0.60 |" in page
    assert "| Output | $1.70 |" in page
    assert "Cache Read" not in page


def test_model_page_includes_nonzero_cache_read_row():
    page = sync_catalog.render_model_page(
        {
            "id": "test/cache",
            "context_length": 1000,
            "max_output_length": 100,
            "pricing": {
                "input": "0.00000154",
                "output": "0.00000484",
                "cache_read": "0.000000286",
            },
        }
    )

    assert "| Cache Read | $0.286 |" in page


def test_model_page_links_huggingface_source_ids():
    page = sync_catalog.render_model_page(
        {
            "id": "test/model",
            "hugging_face_id": "org/model",
            "context_length": 1000,
            "max_output_length": 100,
            "pricing": {
                "input": "0.000001",
                "output": "0.000002",
            },
        }
    )

    assert "| **HuggingFace** | [`org/model`](https://huggingface.co/org/model) |" in page


def test_model_page_renders_registry_uri_without_huggingface_link():
    page = sync_catalog.render_model_page(
        {
            "id": "anthropic/claude-sonnet-5",
            "hugging_face_id": "azureml://registries/azureml-anthropic/models/claude-sonnet-5/versions/2",
            "context_length": 200000,
            "max_output_length": 8192,
            "pricing": {
                "input": "0.000002",
                "output": "0.000010",
            },
        }
    )

    assert (
        "| **Source** | `azureml://registries/azureml-anthropic/models/claude-sonnet-5/versions/2` |"
        in page
    )
    assert "https://huggingface.co/azureml://" not in page


def test_model_page_links_web_source_urls_without_huggingface_prefix():
    page = sync_catalog.render_model_page(
        {
            "id": "vendor/web-source",
            "hugging_face_id": "https://example.com/models/web-source",
            "context_length": 1000,
            "max_output_length": 100,
            "pricing": {
                "input": "0.000001",
                "output": "0.000002",
            },
        }
    )

    assert (
        "| **Source** | [`https://example.com/models/web-source`](https://example.com/models/web-source) |"
        in page
    )
    assert "https://huggingface.co/https://" not in page


def test_pricing_page_adds_cache_read_column_only_when_needed():
    without_cache = sync_catalog.render_pricing(
        [
            {
                "id": "test/without-cache",
                "context_length": 1000,
                "quantization": "managed",
                "pricing": {
                    "input": "0.0000006",
                    "output": "0.0000017",
                    "cache_read": "0",
                },
            }
        ]
    )
    with_cache = sync_catalog.render_pricing(
        [
            {
                "id": "test/with-cache",
                "context_length": 1000,
                "quantization": "managed",
                "pricing": {
                    "input": "0.00000154",
                    "output": "0.00000484",
                    "cache_read": "0.000000286",
                },
            }
        ]
    )

    assert "| Model | Input | Output | Quant | Context |" in without_cache
    assert "Cache Read" not in without_cache
    assert "| Model | Input | Output | Cache Read | Quant | Context |" in with_cache
    assert "| `test/with-cache` | $1.54 | $4.84 | $0.286 | `managed` | 1,000 |" in with_cache


def test_parse_model_page_reads_cache_read_row(tmp_path):
    path = tmp_path / "model.mdx"
    path.write_text(
        """<Info>
  Model id: `test/disk-model`
</Info>

| | |
|---|---|
| **Context length** | 1,000 tokens |
| **Quantization** | `managed` |

| | per million tokens |
|---|---|
| Input | $1.54 |
| Output | $4.84 |
| Cache Read | $0.286 |
"""
    )

    parsed = sync_catalog.parse_model_page(path)

    assert parsed is not None
    assert sync_catalog.display_pricing(parsed) == {
        "input": "$1.54",
        "output": "$4.84",
        "cache_read": "$0.286",
    }


def test_zero_cache_read_disk_row_does_not_force_pricing_column(tmp_path):
    path = tmp_path / "model.mdx"
    path.write_text(
        """<Info>
  Model id: `test/disk-model`
</Info>

| | |
|---|---|
| **Context length** | 1,000 tokens |
| **Quantization** | `managed` |

| | per million tokens |
|---|---|
| Input | $1.54 |
| Output | $4.84 |
| Cache Read | Free |
"""
    )
    parsed = sync_catalog.parse_model_page(path)

    assert parsed is not None
    page = sync_catalog.render_pricing([parsed])

    assert "Cache Read" not in page


def test_skip_page_patch_adds_nonzero_cache_read_row(tmp_path):
    path = tmp_path / "partner.mdx"
    path.write_text(
        """## Pricing

{/* sync:pricing:start */}

| | per million tokens |
|---|---|
| Input | $0.60 |
| Output | $1.70 |

{/* sync:pricing:end */}

## Cost example

{/* sync:cost-example:start */}
old
{/* sync:cost-example:end */}
"""
    )

    changed = sync_catalog.patch_skip_page(
        path,
        {
            "pricing": {
                "input": "0.00000154",
                "output": "0.00000484",
                "cache_read": "0.000000286",
            }
        },
    )

    assert changed is True
    text = path.read_text()
    assert "| Input  | $1.54 |" in text
    assert "| Output | $4.84 |" in text
    assert "| Cache Read | $0.286 |" in text


def test_skip_page_patch_removes_zero_cache_read_row(tmp_path):
    path = tmp_path / "partner.mdx"
    path.write_text(
        """## Pricing

{/* sync:pricing:start */}

| | per million tokens |
|---|---|
| Input | $1.54 |
| Output | $4.84 |
| Cache Read | $0.286 |

{/* sync:pricing:end */}

## Cost example

{/* sync:cost-example:start */}
old
{/* sync:cost-example:end */}
"""
    )

    changed = sync_catalog.patch_skip_page(
        path,
        {
            "pricing": {
                "input": "0.00000154",
                "output": "0.00000484",
                "cache_read": "0",
            }
        },
    )

    assert changed is True
    text = path.read_text()
    assert "| Input  | $1.54 |" in text
    assert "| Output | $4.84 |" in text
    assert "Cache Read" not in text
