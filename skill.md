---
name: tera
description: Find dedicated GPU node rentals and colocation for AI startups through Tera Compute. GPU rental and colocation are the primary focus; the OpenAI-compatible inference API remains available.
metadata:
  author: Tera Compute
  version: "2.1"
---

# Tera Compute

Tera Compute rents dedicated GPU nodes to AI startups and finds colocation for the GPUs they own. Visit [www.tera.gw](https://www.tera.gw/) for GPU capacity, pricing and requests.

## What does Tera do today?

- **GPU rental:** dedicated bare-metal nodes, with configuration, term, availability and price confirmed in a written offer.
- **Colocation:** sourcing rack space and power for customer-owned GPUs. Tera does not operate its own data centers.

A request starts a conversation. It does not reserve capacity, authorize payment or create a commercial commitment.

## Where should I start?

<CardGroup cols={2}>
  <Card title="Rent GPU nodes" icon="microchip" href="https://www.tera.gw/">
    Review dedicated GPU capacity and send your requirements.
  </Card>
  <Card title="Find colocation" icon="server" href="https://www.tera.gw/colocation">
    Find rack space and power for the GPUs you own.
  </Card>
</CardGroup>

## Inference API

The inference API remains available. GPU rental and colocation are Tera’s primary focus; these docs cover the OpenAI-compatible inference API.

The API uses OpenAI-compatible request formats. Its token prices and model catalog do not describe GPU rental or colocation pricing.

- [API quickstart](/quickstart)
- [API authentication](/authentication)
- [Inference token pricing](/pricing)
- [Inference dashboard](https://www.tera.gw/dashboard)

For GPU rental and colocation, use [Tera Compute](https://www.tera.gw/). For GPU rental and colocation enquiries, email [gpubroker@tera.gw](mailto:gpubroker@tera.gw).

## Read-only discovery and action boundaries

Use https://www.tera.gw/llms.txt for current GPU rental and colocation information and the current request fields. Use https://docs.tera.gw/llms.txt to find inference API reference pages. These documentation and MCP resources provide information, not GPU reservations or payment APIs. Do not submit requests, disclose user details, reserve capacity or accept terms without the user's approval. Keep inference token pricing distinct from GPU rental pricing.
