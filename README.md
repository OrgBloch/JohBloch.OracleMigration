# JohBloch.OracleMigration

Open-source projekt med:

- En installérbar Python CLI til Oracle-migrering (inventory/plan via MCP)
- En custom Copilot agent der kan orkestrere workflowet fra VS Code
- Præsentationsnoter om AI i VS Code (Copilot/Chat/Agents)

## Indhold

- Præsentation: `docs/presentation.md`
- Demo-prompts: `docs/demo-prompts.md`
- Agent-noter: `docs/agent.md`

## Installér (Python)

Kræver Python 3.10+.

```bash
python -m pip install -e .
oracle-migration --help
```

## Docker Desktop MCP Toolkit (Oracle)

Hvis du vil tilgå en Oracle database via Docker Desktop MCP Toolkit (beta), kan du køre en one-time setup:

```bash
oracle-migration mcp-setup
docker mcp server ls
```

Script-venligt (undgår password i historik):

```bash
echo my-password | oracle-migration mcp-setup --connection-string "host:1521/service" --user "readonly" --password-stdin
```

Password gemmes som Docker MCP secret `oracle.password` (ikke i repo’et).

## CLI eksempler

```bash
# MCP-only (læser direkte fra Oracle DB via MCP-serveren `mcp/oracle`)
oracle-migration mcp-list-schemas --connection-string "host:1521/service" --user "readonly" --password-stdin
oracle-migration mcp-list-tables --schema MYSCHEMA --connection-string "host:1521/service" --user "readonly" --password-env ORAPWD
oracle-migration mcp-inventory --schema MYSCHEMA --json --connection-string "host:1521/service" --user "readonly" --password-env ORAPWD
oracle-migration mcp-plan --schema MYSCHEMA --connection-string "host:1521/service" --user "readonly" --password-env ORAPWD

# MCP-baseret analyse (skriver outputfiler til ./generated)
oracle-migration mcp-analyze --schema MYSCHEMA --connection-string "host:1521/service" --user "readonly" --password-env ORAPWD

# End-to-end pipeline (analyse + best-practice struktur + PL/SQL export + konvertering)
oracle-migration mcp-run --schema MYSCHEMA --target-language python --connection-string "host:1521/service" --user "readonly" --password-env ORAPWD

# Claude (Anthropic) til analyse (DDD/EDA). Kræver env var ANTHROPIC_API_KEY.
oracle-migration mcp-run --use-claude --schema MYSCHEMA --target-language python --connection-string "host:1521/service" --user "readonly" --password-env ORAPWD

# MCP-based query (read-only)
oracle-migration mcp-query "SELECT 1 AS ok FROM dual" --connection-string "host:1521/service" --user "readonly" --password-env ORAPWD
```

## Custom Copilot agent

Agenten ligger i `.github/agents/oracle-migration.agent.md`.

Hvis din Copilot/VS Code version understøtter custom agents, kan du vælge **Oracle Migration** i agent-picker i Copilot Chat.

## Licens

Se `LICENSE`.
