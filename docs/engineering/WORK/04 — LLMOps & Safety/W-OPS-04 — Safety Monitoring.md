# W-OPS-04 — Safety Monitoring

## OBJECTIVE

Detect unsafe AI behavior during execution.

## REQUIRED SIGNALS

- prompt injection indicators;
- tool misuse;
- authorization mismatch;
- sensitive output indicators;
- abnormal request volume;
- repeated failed authorization;
- unexpected tool sequences.

## RULE

Safety monitoring must not depend only on the LLM self-report.

Use deterministic checks wherever possible.

## RESPONSE

Risk detected
→ record event
→ block/quarantine when policy requires
→ terminate or require approval when appropriate.

## ACCEPTANCE

Safety violations generate observable deterministic events and cannot silently pass.