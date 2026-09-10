# W-ORC-03 — Tools

## OBJECTIVE

Complete a typed, permission-aware tool execution layer.

## REQUIRED FLOW

Agent
→ ToolRegistry
→ tool metadata validation
→ authorization check
→ argument validation
→ execution
→ normalized ToolResult
→ Agent

## TOOL CONTRACT

Every tool must declare:

- tool_name;
- description;
- input schema;
- output schema;
- required permissions;
- side_effect classification;
- timeout;
- whether human approval is required.

## EXECUTION

Do not allow arbitrary callable execution.

Resolve the tool only through `ToolRegistry`.

Validate arguments before execution.

Validate tenant/user context before execution.

Normalize output into a typed result.

## DANGEROUS ACTIONS

If a tool is classified as dangerous:

Agent
→ ApprovalManager
→ user approval
→ execute

Rejected approval:
→ explicit rejection state.

## TIMEOUT

Every tool call must have a bounded timeout.

## TESTS

- valid tool;
- unknown tool;
- invalid arguments;
- missing permission;
- wrong tenant;
- timeout;
- cancellation;
- approval required;
- approval denied;
- execution error.

## FORBIDDEN

- executing arbitrary Python from model output;
- passing raw model text directly into subprocess/shell;
- bypassing ToolRegistry;
- bypassing authorization.

## ACCEPTANCE

Every tool execution is typed, permission-aware, tenant-aware and bounded.