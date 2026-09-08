# REPAIR-14 — TOK-01 CANONICAL TOKENIZER ADOPTION

Finding:
TOK-01

Objective:
Migrate production token-sensitive paths away from inaccurate regex-only accounting.

Required invariant:

Production quota/accounting/context-budget decisions use the canonical model-aware tokenizer where supported.

Required work:

- locate all hot-path estimate_tokens usage;
- classify estimation vs authoritative accounting;
- migrate accounting and budgeting paths to TokenCounter/BPETokenizer;
- preserve cheap fallback only where explicitly appropriate;
- document estimator limitations.

Required validation corpus:

- Vietnamese
- Chinese
- Japanese
- Korean
- English
- JSON
- Python
- SQL
- Markdown

Compare estimator against canonical tokenizer.

Do not delete the regex helper globally before migration is complete.