# Security boundaries

AgentForge is a portfolio demonstration, not a production-hardened CRM.

## Currently implemented
- Deterministic mock-LLM tests for runtime and tool dispatch
- Tool-level validation and selected configurable guardrails
- A destructive demo database reset route disabled by default and restricted to loopback clients when enabled

## Not implemented
- Authentication and authorization for GraphQL mutations, agent chat, and streaming routes
- Multi-tenant data isolation or protected access to stored traces
- Full secret management, audit retention, production monitoring, and threat-model validation

**Do not publish this API or connect it to real customer data.** Run it on localhost with synthetic seed data. The `ENABLE_DEMO_RESET` environment flag must remain false outside an isolated local demo.

Do not include real API keys, tokens, user data, or credentials in commits or issues. If you discover a security problem, avoid posting working exploits or secrets in a public issue; first contact the repository owner privately through GitHub.
