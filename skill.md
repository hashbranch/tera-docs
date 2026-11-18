---
name: tera
description: Find dedicated GPU node rentals and colocation for AI startups through Tera Compute. Read current services first; consult the deprecated inference API reference only for existing customers.
metadata:
  author: Tera Compute
  version: "2.0"
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

## Deprecated: Inference API

<Warning>
The Tera inference API is being deprecated. These reference pages remain for existing customers. No sunset date has been announced here. Contact your Tera representative about migration timing.
</Warning>

The legacy API uses OpenAI-compatible request formats. Its token prices and model catalog do not describe GPU rental or colocation pricing.

- [Legacy API quickstart](/quickstart)
- [Legacy API authentication](/authentication)
- [Legacy token pricing](/pricing)
- [Inference dashboard](https://www.tera.gw/dashboard)

For current services, use [Tera Compute](https://www.tera.gw/). For GPU rental and colocation enquiries, email [gpubroker@tera.gw](mailto:gpubroker@tera.gw).

## Read-only discovery and action boundaries

Use https://www.tera.gw/llms.txt for current GPU rental and colocation information and the current request fields. Use https://docs.tera.gw/llms.txt to find legacy inference reference pages. These documentation and MCP resources provide information, not GPU reservations or payment APIs. Do not submit requests, disclose user details, reserve capacity or accept terms without the user's approval. Do not infer a sunset date or present legacy token prices as current GPU rental prices.
