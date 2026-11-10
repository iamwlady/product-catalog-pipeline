# Product catalog pipeline

Turns a list of new products into a priced, described, translated and validated import file for an online shop. AI writes and translates the copy, business rules in code check every row, and a person signs off before anything goes live.

## The problem

Adding new products to a shop usually means filling a spreadsheet by hand: SKUs, prices worked out from cost, a description per product, then every description again in each language. It is slow, and a price below margin or a missing translation only shows up once customers see it.

## How it works

```
brief.yaml ─► plan (code) ─► describe (AI) ─► translate (AI) ─► validate (code) ─► review (person) ─► import.csv
              SKUs, prices    English          ro / de           margin, .90 price,  approves or       only if valid
              from cost       descriptions                       length, claims,     edits the draft   and approved
                                                                 every language
```

| Step | Done by | Why |
| --- | --- | --- |
| SKUs, prices, stock | Code (`plan_items`, `rules.py`) | Prices come from cost x category markup, never from a language model |
| Descriptions | AI (`prompts/describe.md`) | First drafts in the shop's tone, using only the facts given |
| Translations | AI (`prompts/translate.md`) | One call per language; names, units and origins stay as they are |
| Validation | Code (`rules.py`) | 45% minimum margin, prices ending in .90, 300-character limit, banned claims, every product in every language |
| Approval | **Person** | `finalize` writes `import.csv` only with `--approved-by` and a clean validation |

Guardrails:

- The model's answer must be JSON with **exactly** the requested SKUs. If not, it gets one retry, then the run stops without writing anything.
- Rules live in code, not in the prompt, so the model cannot argue past them.
- Cost prices stay in the draft for checking and are removed from the import file.
- `review.md` lists every problem as a checklist, plus every product in every language with its price, so the reviewer reads everything in one place.
- `approval.txt` records who approved the file and when. If a later edit fails validation, the old `import.csv` is deleted.

## Run it

```bash
pip install -r requirements.txt

# Offline demo: replays recorded model responses, no API key needed
python pipeline.py draft --brief examples/brief.yaml --out out/new-products --mock

# With the real model
export ANTHROPIC_API_KEY=...
python pipeline.py draft --brief examples/brief.yaml --out out/new-products

# Read out/new-products/review.md, edit draft.csv if needed, then re-check
python pipeline.py validate --brief examples/brief.yaml --out out/new-products

# Sign off
python pipeline.py finalize --brief examples/brief.yaml --out out/new-products --approved-by "Your Name"
```

Try breaking it: set a price in `draft.csv` to `12.00`, or add "the best" to a description, and run `finalize`. It refuses and lists each problem in `review.md`.

## Repository

```
pipeline.py              draft / validate / finalize
rules.py                 columns, markups, margin, pricing and wording rules
prompts/                 the two prompts the model receives
examples/brief.yaml      new products for a fictional coffee shop
examples/fixtures.json   recorded model responses for --mock
examples/output/         draft, review and approved import file from the example
```

To use it for another shop, change the categories, markups and banned words in `rules.py` and the column names in `IMPORT_COLUMNS` to match your platform's import format.

## License

MIT
