# AI i VS Code 1.110 — præsentationsnoter

Formål: give en slide-/demo-venlig oversigt over kommando-typer, hvordan man laver en plan for kodekonvertering, og hvilke agent-typer man typisk bruger i VS Code.

## 1) Kommando-typer

I praksis vil du typisk se disse “typer” af interaktioner i VS Code med Copilot:

### Inline forslag ("ghost text")

- Autocomplete mens du skriver (Tab for at acceptere)
- Godt til små ændringer, boilerplate, navngivning og trivielle funktioner

### Chat-skabeloner (ofte skrevet som `#...` i Copilot Chat)

Bruges til at styre *format og intention* i svaret.

Eksempler:

- `#explain` — forklar kode/fil
- `#fix` — find fejl og foreslå rettelser
- `#refactor` — forbedr struktur uden at ændre adfærd
- `#test` — generér tests
- `#review` — code review med fokus på læsbarhed/risiko
- `#document` — generér dokumentations-tekst

Bemærk: de konkrete `#`-skabeloner kan variere lidt mellem versioner og enterprise-opsætninger.

### System-/session-kommandoer (ofte skrevet som `/...`)

Bruges til at styre chat-sessionen.

Eksempler:

- `/help` — vis tilgængelige chat-kommandoer
- `/clear` — ryd chatten
- `/reset` — nulstil kontekst i chatten

Vigtigt: Modelvalg sker typisk via UI (model-dropdown) i VS Code, ikke via en `/set session target`-slash-kommando.

### Kontekst-værktøjer og “scopes” (ofte skrevet som `@...`)

Bruges til at fortælle *hvilken kontekst* eller *hvilket værktøj* Copilot skal anvende.

Eksempler:

- `@workspace` — hele projektet
- `@file` — nuværende fil
- `@folder` — en mappe
- `@terminal` — terminal-kontekst / kommando-forslag
- `@tests` — test-relaterede opgaver
- `@git` — diffs/commits

Bemærk: listen afhænger af installerede extensions og Copilot-funktionalitet.

## 2) Plan for kodekonvertering (migrering)

En god migrering/konvertering lykkes oftest med en bevidst plan. Brug gerne denne struktur som “skabelon”:

1. Afgrænsning
   - Hvad skal konverteres (fil/modul/hele repo)?
   - Hvad er målformatet (fx Oracle SQL → PostgreSQL, .NET Framework → .NET 8, JS → TS)?

2. Analyse
   - Kortlæg afhængigheder og integrationer
   - Identificér risici (API-breaking changes, datamodel, performance)

3. Strategi
   - Fil-for-fil vs. modul-for-modul vs. "big bang"
   - Aftal "definition of done" (build/test/feature parity)

4. Implementering
   - Lav ændringer i små batches
   - Hold ændringer review-venlige

5. Test & validering
   - Automatisér tests (unit/integration)
   - Kør end-to-end flows der matcher de vigtigste use cases

6. Dokumentation
   - Opdatér README, kørsel, arkitektur, beslutninger og kendte begrænsninger

## 3) Agent-typer (arbejdsmåder)

Tænk på “agenter” som forskellige måder at arbejde på — ikke nødvendigvis separate produkter.

- Coding agent: implementerer/refaktorerer konkret kode
- Workspace agent: arbejder på tværs af mange filer, og kan lave større ændringer
- Terminal agent: foreslår og forklarer kommandoer, setup og scripts
- Test agent: genererer og forbedrer tests
- Git agent: forklarer diffs og hjælper med commit-beskeder

## 4) Claude i VS Code

I VS Code vælges model typisk i Copilot Chat UI (model-selector), eller via settings/enterprise policy.

Hvis nogen siger “`/set session target`”, så er det et mønster fra andre miljøer — i VS Code er det oftest:

- Vælg model i chat-panelets dropdown
- Alternativt: indstillinger for Copilot Chat (hvis tilgængeligt i din installation)

## 5) Demo-scenarier

1. Forklar en fil

- `@file #explain` + “Forklar hvad denne fil gør og hvilke risici der er.”

2. Migreringsplan

- `@workspace #generate` + “Lav en migreringsplan fra X til Y, inkl. delopgaver og teststrategi.”

3. Generér tests

- `@file #test` + “Lav unit tests for de vigtigste edge cases.”

---

Se også `docs/demo-prompts.md` for flere kopi/indsæt-eksempler.
