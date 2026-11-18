# Docs SEO/AEO review, November 18, 2026

This branch updates Tera's public description to dedicated GPU node rentals and colocation for AI startups. The inference API remains available, while GPU rental and colocation are the primary focus.

The introduction is the source for the current-services section in `llms.txt`, `llms-full.txt` and `skill.md`. `scripts/public_docs.py` rebuilds the exports from navigation-listed pages. The catalog sync runs it at the end, including hand-maintained model pages, so the agent exports stay aligned with the current introduction. CI detects export drift.

Mintlify supports root-level overrides for [llms files](https://www.mintlify.com/docs/ai/llmstxt) and [skill.md](https://www.mintlify.com/docs/ai/skillmd). The custom skill supplies descriptions for agent-card and MCP skill resources. The hosted server-card description is Mintlify-managed and generic; after deployment, inspect the generated agent card and MCP resources rather than assuming that a file diff proves the hosted result.

Validation: 17 Python tests, Mintlify strict validation/build, configuration JSON schema and broken-links checks passed. Introduction, inference pricing, API reference and a hand-maintained model page were reviewed at 390px and 1440px without document overflow. Screenshots and viewport measurements are in this folder, which is excluded from Mintlify publication.

Publish the landing companion before or alongside this change so the new colocation link is live. Check `/`, `/llms.txt`, `/llms-full.txt`, `/skill.md`, `/.well-known/agent-card.json`, `/.well-known/mcp/server-card.json` and MCP skill resources on the hosted preview and after release.
