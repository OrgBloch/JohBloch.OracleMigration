# Custom Copilot agent

Denne workspace indeholder en custom agent:

- `.github/agents/oracle-migration.agent.md`

## Sådan bruger du den i VS Code

1. Åbn Copilot Chat.
2. Vælg agenten **Oracle Migration** i agent-picker (hvis din Copilot-version understøtter custom agents).
3. Giv agenten en opgave (fx: “Lav inventory og plan for schema `MYSCHEMA` via MCP”).

## Installér Python CLI

```bash
python -m pip install -e .
oracle-migration --help
```

## Opsæt Docker Desktop MCP Toolkit (Oracle)

Kør én gang (interaktivt):

```bash
oracle-migration mcp-setup
docker mcp server ls
```

Script-venligt eksempel:

```bash
echo my-password | oracle-migration mcp-setup --connection-string "host:1521/service" --user "readonly" --password-stdin
```

Det sætter `oracle.password` i Docker MCP secret store og skriver Oracle MCP config (connection string + user).

## Kør MCP-kommandoer (ingen filer)

Eksempel (script-venligt):

```bash
$env:ORAPWD='my-password'
oracle-migration mcp-inventory --schema MYSCHEMA --json --connection-string "host:1521/service" --user "readonly" --password-env ORAPWD
oracle-migration mcp-plan --schema MYSCHEMA --connection-string "host:1521/service" --user "readonly" --password-env ORAPWD
oracle-migration mcp-analyze --schema MYSCHEMA --connection-string "host:1521/service" --user "readonly" --password-env ORAPWD
```
