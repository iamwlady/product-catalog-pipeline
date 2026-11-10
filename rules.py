"""Business rules for the shop's import file. They live in code, not in prompts,
so the model cannot talk its way past them."""
import math

IMPORT_COLUMNS = ["sku", "name", "category", "price_eur", "stock", "lang", "description"]
DRAFT_COLUMNS = IMPORT_COLUMNS[:4] + ["cost_eur"] + IMPORT_COLUMNS[4:]  # cost stays internal

CATEGORY_PREFIX = {"Coffee beans": "BEAN", "Brewing gear": "GEAR", "Accessories": "ACC"}
MARKUP = {"Coffee beans": 2.2, "Brewing gear": 2.4, "Accessories": 2.6}  # price = cost x markup
MIN_MARGIN = 0.45  # never sell below 45% gross margin
MAX_DESCRIPTION = 300
BANNED_WORDS = ["best", "perfect", "guaranteed", "100%", "cel mai bun", "perfekt", "garantiert"]


def price_from_cost(category, cost):
    """Cost x category markup, rounded up to the shop's .90 price ending."""
    raw = cost * MARKUP[category]
    return math.floor(raw) + 0.90 if raw - math.floor(raw) <= 0.90 else math.floor(raw) + 1.90


def validate(rows, languages):
    """Returns human-readable problems; an empty list means the file can be imported."""
    problems, seen, skus_by_lang = [], set(), {}
    for i, r in enumerate(rows, start=2):  # row 1 is the header
        where = f"row {i} ({r.get('sku', '?')}, {r.get('lang', '?')})"
        missing = [c for c in DRAFT_COLUMNS if not str(r.get(c, "")).strip()]
        if missing:
            problems.append(f"{where}: empty {', '.join(missing)}")
            continue
        key = (r["sku"], r["lang"])
        if key in seen:
            problems.append(f"{where}: duplicate SKU and language")
        seen.add(key)
        skus_by_lang.setdefault(r["lang"], set()).add(r["sku"])

        if r["category"] not in MARKUP:
            problems.append(f"{where}: unknown category '{r['category']}'")
            continue
        price, cost = float(r["price_eur"]), float(r["cost_eur"])
        if price <= 0 or (price - cost) / price < MIN_MARGIN:
            problems.append(f"{where}: price €{price:.2f} is below the {int(MIN_MARGIN * 100)}% minimum margin (cost €{cost:.2f})")
        if round(price % 1, 2) != 0.90:
            problems.append(f"{where}: price €{price:.2f} should end in .90")
        if int(r["stock"]) < 0:
            problems.append(f"{where}: negative stock")
        text = r["description"]
        if len(text) > MAX_DESCRIPTION:
            problems.append(f"{where}: description is {len(text)} characters (max {MAX_DESCRIPTION})")
        hits = [w for w in BANNED_WORDS if w in text.lower()]
        if hits:
            problems.append(f"{where}: claims to avoid: {', '.join(hits)}")

    all_skus = set().union(*skus_by_lang.values()) if skus_by_lang else set()
    for lang in languages:
        gaps = all_skus - skus_by_lang.get(lang, set())
        if gaps:
            problems.append(f"language '{lang}' is missing {len(gaps)} product(s): {', '.join(sorted(gaps))}")
    return problems
