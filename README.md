# Mathem Agent

Personlig prototyp för en automatisk, värdeoptimerad matkasse ovanpå Mathem.

## Project overview and offline review

Mathem Agent is a personal Python prototype for planning a household's weekly
meals, comparing grocery products and preparing a Mathem shopping basket. It
provides a Typer CLI, an optional Streamlit interface and FastMCP tools. HTTPX
and Playwright support the retailer connector; pytest covers parsing, product
scoring, local session helpers and weekly-run recovery.

Meal selection uses recipe templates, heuristic product scoring and seeded
selection. The proposed development work is documented in [ROADMAP.md](ROADMAP.md).

### Review without a live account

Use Python 3.11 or newer. From a checkout of this repository:

```bash
uv sync --extra dev --extra app
uv run mathem-agent demo --save plan-demo.json
uv run pytest -q
```

The demo uses the built-in sample catalog, and the tests use temporary files and
mock clients. These commands do not sign in to Mathem, install a weekly job or
modify a live basket. Real account setup and scheduled basket updates are
separate, optional flows described below.

Session cookies and browser profiles are stored outside the repository by
default under `~/.mathem-agent/`. Keep local account state, addresses and
shopping records private; use fictional fixtures for development and review.

Målflödet är:

1. logga in eller skapa Mathem-kontot en gång,
2. spara den lokala sessionen,
3. kör varje vecka utan synlig webbläsare,
4. hämta aktuella Mathem-priser, kampanjer och prismatchprodukter,
5. konstruera veckans meny utifrån dina preferenser,
6. lägga alla valda produkter automatiskt i Mathem-varukorgen,
7. låta dig öppna Mathem-appen eller din vanliga webbläsare när du vill granska och beställa.

Veckojobbet skickar inte den bindande ordern och genomför inte betalningen. Det fyller den serverbaserade Mathem-varukorgen automatiskt.

## Installation från noll

```bash
git clone https://github.com/Henrik-KM/Mathem-agent.git
cd Mathem-agent
uv sync --extra app
uv run mathem-agent setup
```

`setup` gör två saker:

- öppnar Mathem en enda gång för kontoregistrering eller inloggning,
- installerar därefter ett lokalt bakgrundsjobb som sköter framtida veckor headless.

Fyll i de uppgifter Mathem begär direkt på deras webbplats, godkänn villkoren och lägg in leveransadressen. När du är inloggad går du tillbaka till terminalen och trycker Enter.

Den synliga Playwright-webbläsaren behövs alltså vid första registreringen. Den öppnas inte under normala veckokörningar.

Standardinställningen är:

- måndag klockan 09:00,
- tidszon `Europe/Stockholm`,
- två personer,
- fyra middagar,
- maxbudget 850 kr,
- automatisk cart-add aktiverad.

Kontrollera allt med:

```bash
uv run mathem-agent weekly status
```

## Hur schemat fungerar

Operativsystemet gör en liten kontroll dagligen vid den konfigurerade tiden. Själva matkassen skapas bara en gång per veckoperiod.

Det dagliga kontrolljobbet används för att datorn ska kunna komma ikapp om den var avstängd eller sov vid den exakta veckotiden. Jobbet är idempotent:

- samma veckoplan återanvänds vid en omkörning,
- redan tillagda varurader läggs inte till igen,
- en delvis misslyckad körning fortsätter med kvarvarande varor,
- ett osäkert API-resultat återförs inte automatiskt, eftersom det skulle kunna dubblera en vara.

Alla planer och körstatusar sparas lokalt under:

```text
~/.mathem-agent/weekly-runs/
```

Loggen ligger i:

```text
~/.mathem-agent/weekly.log
```

## Anpassa den automatiska matkassen

Exempel: söndag klockan 18:00, två personer och fem middagar:

```bash
uv run mathem-agent weekly configure \
  --day SUN \
  --time 18:00 \
  --people 2 \
  --meals 5 \
  --max-budget 1000 \
  --preferences "snabbt, mycket protein, varierat, inte för starkt" \
  --avoid "svamp"
```

Kommandot sparar konfigurationen och uppdaterar Windows Task Scheduler eller användarens `crontab`, beroende på operativsystem.

Installera om schemat från sparad konfiguration:

```bash
uv run mathem-agent weekly install
```

Ta bort endast bakgrundsschemat:

```bash
uv run mathem-agent weekly uninstall
```

Kontodata, sessioner och tidigare planer raderas inte av `uninstall`.

## Testa veckoflödet direkt

Skapa veckans plan utan att ändra varukorgen:

```bash
uv run mathem-agent weekly run --dry-run
```

Kör den riktiga veckoloopen direkt:

```bash
uv run mathem-agent weekly run
```

En andra körning under samma period ska rapportera `skipped` och inte lägga till produkterna igen.

## Konto och session

Sessionen sparas lokalt under:

```text
~/.mathem-agent/
```

Du behöver inte öppna Developer Tools, kopiera cookies eller lägga lösenord i `.env`.

Kontrollera kontosessionen:

```bash
uv run mathem-agent auth status
```

Om du redan har ett Mathem-konto:

```bash
uv run mathem-agent setup --existing-account
```

Den automatiska körningen försöker uppdatera sessionen headless. Om Mathem kräver en helt ny interaktiv inloggning markeras körningen som `needs_attention`; ingen webbläsare öppnas automatiskt. Då räcker det att köra:

```bash
uv run mathem-agent setup --existing-account
```

## Öppna varukorgen

Produkterna ligger i ditt Mathem-konto och kan därför granskas i Mathem-appen eller i din vanliga webbläsare. Repo:t behöver inte öppna den separata setup-profilen varje vecka.

```bash
uv run mathem-agent checkout
```

Detta öppnar Mathem i din vanliga standardwebbläsare. Den sparade Playwright-profilen används endast om du uttryckligen begär det:

```bash
uv run mathem-agent checkout --managed-profile
```

## Manuell planering och cart-add

Du kan fortfarande arbeta manuellt:

```bash
uv run mathem-agent plan \
  --people 2 \
  --meals 4 \
  --max-budget 850 \
  --preferences "snabbt, mycket protein, inte för starkt" \
  --avoid "svamp" \
  --save plan.json
```

Torrkörning:

```bash
uv run mathem-agent cart add plan.json
```

Lägg till:

```bash
uv run mathem-agent cart add plan.json --confirm
```

## Lokal app

```bash
uv run streamlit run app.py
```

Appen visar meny, estimerad kostnad och aggregerad varukorg. Det automatiska veckoschemat körs separat av operativsystemet.

## MCP-server

```bash
uv run mathem-mcp
```

Exponerade MCP-tools:

- `search_products`
- `list_prismatch_products`
- `list_prismatch_recipes`
- `generate_meal_plan_tool`
- `add_plan_to_cart`

## Sessionssäkerhet

Den lokala Playwright-profilen och exporterade sessionscookies ligger utanför repo:t i `~/.mathem-agent/`. Mathem Agent lagrar inte ditt Mathem-lösenord eller dina betalningsuppgifter. Dela inte katalogen eller dess filer.

En annan lokal katalog kan anges med:

```bash
export MATHEM_AGENT_HOME="/valfri/privat/katalog"
```

Manuell `MATHEM_COOKIE` i `.env` stöds fortfarande som reservlösning.

## Begränsningar

Det här är en personlig prototyp. Mathems sidstruktur, sessionshantering och interna cart-endpoint kan ändras. Om det sker kan connectorn behöva uppdateras.

Produktmatchningen är heuristisk. Kontrollera därför Mathems slutliga varukorg, antal, substitutionsvaror, leveransavgift och totalsumma innan du skickar en bindande beställning.

## License

The original source code and accompanying documentation are licensed under the
[MIT License](LICENSE), copyright (c) 2026 Henrik Klein Moberg.

Dependencies retain their respective licenses. This software license does not
grant rights to retailer branding, externally sourced product content, account
credentials or personal shopping records.
