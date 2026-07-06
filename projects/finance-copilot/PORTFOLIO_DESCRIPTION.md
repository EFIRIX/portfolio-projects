# Finance Copilot

Telegram bot that automates personal finance tracking: upload a CSV bank statement and get category breakdown, weekly reports with week-over-week comparisons, and 1–2 data-driven observations.

## Portfolio Value

- Demonstrates a two-stage categorization pipeline: deterministic rules (keyword dictionary) for ~80% of transactions, LLM fallback for the rest — cost-efficient and resilient.
- Sensitive data handling: card numbers (PAN), account numbers, and counterparty names are stripped before storage; a log filter catches any leaked data.
- Pluggable LLM providers (YandexGPT, GigaChat) behind an abstract interface; works with `LLM_PROVIDER=none` for rule-only mode.
- Multi-bank CSV support via configurable column mapping (`bank_formats.yaml`).

## Public Snapshot

The public version excludes `.env`, virtual environments, logs, and local runtime data. Test CSV files contain虚构 data only.
