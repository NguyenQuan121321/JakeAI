# ADR-002: Two-Zone Stable Prefix Prompt Architecture for Provider Cache Optimization

## Status
Accepted

## Context
Frontier model providers (Anthropic Claude 3.5 Sonnet, Google Gemini 1.5/2.0 Flash/Pro, OpenAI GPT-4o) offer prompt caching discounts (up to 80% price reduction and 80% Time-to-First-Token acceleration) when prompt prefixes meet threshold length ($\ge 1,024$ tokens) and remain byte-for-byte identical across turns.

A naive prompt architecture groups the entire repository skeleton into a single block alongside ongoing edits. However, modifying even one file or function changes the entire skeleton hash, invalidating the provider prompt cache on every turn and destroying the 40-60% token savings model.

## Decision
We partition the model prompt payload into two distinct caching zones separated by an explicit provider cache boundary:

### Zone 1: Session-Stable Layer (Cache-Eligible, $\ge 1,024$ tokens)
- **System Directives & Coding Persona**: Fundamental operational instructions, security boundaries, and code quality standards.
- **Global Architectural Invariants**: Target framework versions, language standards, lint rules, and testing requirements.
- **Top-Level Directory Topology & Public Module Signatures**: High-level repository structural skeleton of untouched modules.
- **Provider Cache Breakpoint**: Explicitly marked with upstream cache control metadata (`cache_control: {"type": "ephemeral"}`).

### Zone 2: Dynamic Delta Layer (Billed per turn)
- **Target File Slices**: Exact bounded line ranges of files actively being inspected or edited in the current turn.
- **Agent Scratchpad & Tool Outputs**: Historical messages, tool execution responses, and intermediate reasoning.
- **Active User Instruction**: The specific prompt or follow-up instruction for the current turn.

## Invariant & Regression Verification
- Modifying 1 file in a 50-file repository must leave the prefix byte stream for Zone 1 **100% byte-identical** to the prior turn.
- The prompt compiler asserts that Zone 1 token length exceeds the 1,024-token minimum threshold before placing the provider cache marker.

## Consequences
- **Positive**: Guarantees $\ge 75\%$ prompt cache hit rate across extended multi-turn coding sessions; protects user token budgets from repetitive repository ingestion costs.
- **Negative**: Requires strict compilation separation in the prompt construction pipeline.
