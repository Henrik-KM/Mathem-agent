# Mathem Agent

Personlig prototyp för att bygga en billigare och mer flexibel matkasse ovanpå Mathem.

Den gör följande:

1. skapar eller återansluter en lokal Mathem-session utan manuell cookie-kopiering,
2. hämtar produkt-, pris-, kampanj- och prismatchdata från Mathem,
3. väljer råvaror utifrån pris, jämförpris, prismatch och dina preferenser,
4. konstruerar en veckomeny med konkreta Mathem-produkter,
5. fyller din Mathem-varukorg efter explicit bekräftelse,
6. öppnar samma inloggade webbläsarprofil för leveransval och checkout.

Den sista orderbekräftelsen och betalningen görs av dig direkt hos Mathem. Kontot, personuppgifterna, villkorsgodkännandet och betalningssteget hör till dig och passerar inte genom Mathem Agent.

## Snabbstart från noll

```bash
git clone https://github.com/Henrik-KM/Mathem-agent.git
cd Mathem-agent
uv sync --extra app
uv run mathem-agent setup
```

`setup` installerar Chromium via Playwright, öppnar Mathems registreringssida och skapar en separat lokal webbläsarprofil. Fyll i de uppgifter Mathem begär direkt på deras webbplats, godkänn deras villkor och lägg in din leveransadress. När du är inloggad går du tillbaka till terminalen och trycker Enter.

Mathem Agent sparar därefter sessionen lokalt under:

```text
~/.mathem-agent/
```

Du behöver inte öppna Developer Tools, kopiera cookies eller lägga lösenord i `.env`.

Kontrollera status:

```bash
uv run mathem-agent auth status
```

Om du redan har skapat ett konto:

```bash
uv run mathem-agent setup --existing-account
```

Om sessionen senare blir gammal:

```bash
uv run mathem-agent auth refresh --visible
```

## Sök och kontrollera Mathem-data

```bash
uv run mathem-agent search "kyckling"
uv run mathem-agent prismatch --limit 20
uv run mathem-agent prismatch-recipes --limit 20
```

När en lokal session finns skickas den även vid produktsökningar, så Mathem kan använda ditt inloggade område och din leveranskontext.

## Bygg en meny

```bash
uv run mathem-agent plan \
  --people 2 \
  --meals 4 \
  --max-budget 850 \
  --preferences "snabbt, mycket protein, inte för starkt" \
  --avoid "svamp" \
  --save plan.json
```

Kör först en torrkörning av varukorgen:

```bash
uv run mathem-agent cart add plan.json
```

Lägg sedan varorna i Mathem-varukorgen:

```bash
uv run mathem-agent cart add plan.json --confirm
```

Öppna den inloggade Mathem-varukorgen och slutför leveransval och betalning:

```bash
uv run mathem-agent checkout
```

Samma kommando finns även som:

```bash
uv run mathem-agent cart open
```

## Lokal app

```bash
uv run streamlit run app.py
```

Appen låter dig ange antal personer, antal middagar, budget, preferenser och bortval. Den visar meny, total kostnad och aggregerad varukorg. Kör `uv run mathem-agent setup` en gång innan du använder appens cart-funktion.

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

Du kan välja en annan lokal katalog med:

```bash
export MATHEM_AGENT_HOME="/valfri/privat/katalog"
```

Manuell `MATHEM_COOKIE` i `.env` stöds fortfarande som reservlösning, men behövs normalt inte.

## Begränsningar

Det här är en personlig prototyp. Mathems sidstruktur, sessionshantering och interna cart-endpoint kan ändras. Om det sker kan connectorn behöva uppdateras.

Produktmatchningen är heuristisk. Kontrollera därför meny, antal och produkter innan `cart add --confirm`, och kontrollera alltid Mathems slutliga varukorg, leveransavgift, ersättningsvaror och totalsumma innan du skickar beställningen.
