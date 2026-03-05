# Copilot workspace instructions

Dette repo indeholder:

- En custom Copilot agent i `.github/agents/`
- Et Python-package (`johbloch-oracle-migration`) med CLI `oracle-migration`
- Docs i `docs/`

## Standard arbejdsgang

- Foretræk små, reviewbare ændringer.
- Generér altid en plan før større migreringer.
- Når du konverterer SQL, vær tydelig omkring begrænsninger (især PL/SQL).

## Kommandoer

- Installer (editable): `python -m pip install -e .`
- CLI help: `oracle-migration --help`
