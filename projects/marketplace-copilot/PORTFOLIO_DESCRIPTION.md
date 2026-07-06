# Marketplace Copilot

Web tool that generates marketplace product cards tailored to Wildberries and Ozon character limits, plus SEO keyword drafts and polite review-response templates.

## Portfolio Value

- Platform-specific text generation with hard character limits enforced by code, not prompts — demonstrates a "config-as-business-rules" architecture.
- Validation loop: if generated text exceeds limits, the system issues a shrink request to the LLM rather than mechanical truncation; fallback truncation is flagged.
- Abstract `LLMProvider` interface with GigaChat (primary) and YandexGPT (alternative) implementations.
- Full-stack Next.js 14 (App Router) with TypeScript, unit tests via vitest.

## Public Snapshot

The public version excludes `.env`, `node_modules/`, and build artifacts. No real marketplace API integration — MVP generates text only.
