# Mathem Agent

Personlig prototyp för att bygga en billigare, mer flexibel matkasse ovanpå Mathem.

Den första versionen gör fyra saker:

1. hämtar produkt- och prismatchdata från Mathem,
2. väljer bra råvaror utifrån pris, jämförpris, prismatch, kampanj och preferenser,
3. konstruerar en veckomeny med konkreta Mathem-produkter,
4. fyller din Mathem-varukorg med valda produkter efter explicit bekräftelse.

Den gör inte kortbetalning eller sista orderbekräftelsen. Den praktiska prototypen är: planera automatiskt, lägg i varukorg automatiskt, slutför själv i Mathems checkout.

## Snabbstart

```bash
git clone https://github.com/Henrik-KM/Mathem-agent.git
cd Mathem-agent
uv sync --extra app
cp .env.example .env
```

Logga in på Mathem i webbläsaren och kopiera `Cookie`-headern från en request till `mathem.se` in i `.env` som `MATHEM_COOKIE`, eller lägg den i en lokal `cookie.txt`. Filerna är git-ignorerade.

Testa produktsökning:

```bash
uv run mathem-agent search "kyckling"
```

Lista prismatchade varor:

```bash
uv run mathem-agent prismatch --limit 20
```

Bygg en meny och spara som JSON:

```bash
uv run mathem-agent plan \
  --people 2 \
  --meals 4 \
  --max-budget 850 \
  --preferences "snabbt, mycket protein, inte för starkt" \
  --avoid "svamp" \
  --save plan.json
```

Lägg planens produkter i Mathem-varukorgen:

```bash
uv run mathem-agent cart add plan.json --confirm
```

Öppna sedan Mathem och slutför beställningen själv:

```bash
uv run mathem-agent cart open
```

## Lokal app

```bash
uv run streamlit run app.py
```

Appen låter dig ange antal personer, antal middagar, budget, preferenser och bortval. Den visar meny, total kostnad, varukorg och har en separat bekräftelseknapp för att lägga varorna i Mathem-varukorgen.

## MCP-server

```bash
uv run mathem-mcp
```

Exponerade MCP-tools:

- `search_products`
- `list_prismatch_products`
- `list_prismatch_recipes`
- `generate_meal_plan`
- `add_plan_to_cart`

## Viktiga begränsningar

Det här är en personlig prototyp. Mathems sidstruktur och interna cart-endpoint kan ändras. Om Mathem ändrar sin Next.js-data, cart-API eller sessionshantering kan connectorn behöva uppdateras.

Använd bara ditt eget konto. Lagra inte lösenord i repo:t. Låt `.env` eller `cookie.txt` ligga lokalt.

## Rekommenderat flöde

Kör först `plan`, kontrollera rätter och produkter, byt bort uppenbart dåliga matchningar, kör sedan `cart add`. Eftersom produktmatchning är heuristisk ska den ses som en snabb personlig assistent, inte som ett färdigt konsumentflöde.
