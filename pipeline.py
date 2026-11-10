#!/usr/bin/env python3
"""Product brief -> priced, AI-described, translated and validated shop import CSV, signed off by a person.

    python pipeline.py draft    --brief examples/brief.yaml --out out/new-products [--mock]
    #   review out/new-products/review.md, edit draft.csv if needed
    python pipeline.py validate --brief examples/brief.yaml --out out/new-products
    python pipeline.py finalize --brief examples/brief.yaml --out out/new-products --approved-by "Your Name"
    #   -> out/new-products/import.csv (only if validation passes; cost column removed)
"""
import argparse
import csv
import datetime as dt
import json
import os
import re
import sys

import yaml

import rules

HERE = os.path.dirname(os.path.abspath(__file__))
LANGUAGE_NAMES = {"en": "English", "ro": "Romanian", "de": "German", "fr": "French", "es": "Spanish", "it": "Italian", "hu": "Hungarian", "bg": "Bulgarian"}
FIXTURES = os.path.join(HERE, "examples", "fixtures.json")


# ------------------------------------------------------------- AI access
class Model:
    """Thin wrapper so the pipeline runs against the real API or recorded responses (--mock)."""

    def __init__(self, mock):
        self.mock = mock
        if mock:
            with open(FIXTURES, encoding="utf-8") as f:
                self.fixtures = json.load(f)
        else:
            try:
                import anthropic
            except ImportError:
                sys.exit("Install the SDK (pip install anthropic) or run with --mock")
            if not os.environ.get("ANTHROPIC_API_KEY"):
                sys.exit("Set ANTHROPIC_API_KEY or run with --mock")
            self.client = anthropic.Anthropic()
            self.model = os.environ.get("ANTHROPIC_MODEL", "claude-sonnet-5-5")

    def ask_json(self, prompt, fixture_key, expected_skus):
        if self.mock:
            data = self.fixtures[fixture_key]
        else:
            data = None
            for attempt in range(2):  # one retry if the answer is not usable
                msg = self.client.messages.create(model=self.model, max_tokens=4000,
                                                  messages=[{"role": "user", "content": prompt}])
                data = parse_json_list(msg.content[0].text)
                if data is not None and {d.get("sku") for d in data} == set(expected_skus):
                    break
                prompt += "\n\nYour previous answer was not valid JSON with exactly the requested SKUs. Try again."
        if data is None or {d.get("sku") for d in data} != set(expected_skus):
            sys.exit(f"Model output for '{fixture_key}' did not contain exactly the expected SKUs; nothing was written.")
        return {d["sku"]: d["description"].strip() for d in data}


def parse_json_list(text):
    match = re.search(r"\[.*\]", text, re.S)
    if not match:
        return None
    try:
        data = json.loads(match.group(0))
    except json.JSONDecodeError:
        return None
    return data if isinstance(data, list) else None


def read_prompt(name, **values):
    with open(os.path.join(HERE, "prompts", name), encoding="utf-8") as f:
        text = f.read()
    for k, v in values.items():
        text = text.replace("{" + k + "}", str(v))
    return text


# ------------------------------------------------------------ the steps
def load_brief(path):
    with open(path, encoding="utf-8") as f:
        brief = yaml.safe_load(f)
    for key in ("shop", "products", "languages"):
        if key not in brief:
            sys.exit(f"Brief is missing '{key}'")
    if "en" not in brief["languages"]:
        sys.exit("Brief languages must include 'en' (the source language)")
    for p in brief["products"]:
        if p.get("category") not in rules.CATEGORY_PREFIX:
            sys.exit(f"{p.get('name')}: unknown category '{p.get('category')}'")
    return brief


def plan_items(brief):
    """Deterministic part: SKUs, prices and stock come from rules and the brief, never from the model."""
    counters, items = {}, []
    for p in brief["products"]:
        prefix = rules.CATEGORY_PREFIX[p["category"]]
        counters[prefix] = counters.get(prefix, 0) + 1
        items.append({
            "sku": f"{prefix}-{counters[prefix]:03d}",
            "name": p["name"],
            "category": p["category"],
            "price_eur": f"{rules.price_from_cost(p['category'], float(p['cost_eur'])):.2f}",
            "cost_eur": f"{float(p['cost_eur']):.2f}",
            "stock": str(int(p.get("stock", 0))),
            "facts": p.get("facts", ""),
        })
    return items


def draft(args):
    brief = load_brief(args.brief)
    model = Model(args.mock)
    items = plan_items(brief)
    skus = [i["sku"] for i in items]
    os.makedirs(args.out, exist_ok=True)

    # 1. English descriptions
    listing = "\n".join(f"- {i['sku']}: {i['name']} ({i['category']}). Facts: {i['facts']}" for i in items)
    prompt = read_prompt("describe.md", brief=yaml.safe_dump({"shop": brief["shop"]}, sort_keys=False),
                         items=listing, max_chars=rules.MAX_DESCRIPTION)
    texts = {"en": model.ask_json(prompt, "describe", skus)}
    print(f"Wrote {len(skus)} English descriptions")

    # 2. Translations
    for lang in brief["languages"]:
        if lang == "en":
            continue
        source = json.dumps([{"sku": s, "description": texts["en"][s]} for s in skus], ensure_ascii=False, indent=1)
        prompt = read_prompt("translate.md", items=source, lang=lang, language_name=LANGUAGE_NAMES.get(lang, lang),
                             max_chars=rules.MAX_DESCRIPTION)
        texts[lang] = model.ask_json(prompt, f"translate_{lang}", skus)
        print(f"Translated into {lang}")

    # 3. Draft CSV: one row per product per language
    rows = [{**{k: v for k, v in i.items() if k != "facts"}, "lang": lang, "description": texts[lang][i["sku"]]}
            for lang in brief["languages"] for i in items]
    write_csv(os.path.join(args.out, "draft.csv"), rows, rules.DRAFT_COLUMNS)
    report(args, brief, rows)


def validate(args):
    brief = load_brief(args.brief)
    rows = read_csv(os.path.join(args.out, "draft.csv"))
    return report(args, brief, rows)


def finalize(args):
    brief = load_brief(args.brief)
    rows = read_csv(os.path.join(args.out, "draft.csv"))
    problems = rules.validate(rows, brief["languages"])
    if problems:
        stale = os.path.join(args.out, "import.csv")
        if os.path.exists(stale):
            os.remove(stale)  # never leave an older approved file next to a draft that fails
        report(args, brief, rows)
        sys.exit("Not finalized: fix the problems in review.md first.")
    write_csv(os.path.join(args.out, "import.csv"), rows, rules.IMPORT_COLUMNS)
    with open(os.path.join(args.out, "approval.txt"), "w", encoding="utf-8") as f:
        f.write(f"Approved by {args.approved_by} on {dt.datetime.now().isoformat(timespec='minutes')}\n"
                f"{len(rows)} rows, languages: {', '.join(brief['languages'])}\n")
    print(f"Wrote {os.path.join(args.out, 'import.csv')} ({len(rows)} rows), approved by {args.approved_by}")


# ---------------------------------------------------------------- files
def report(args, brief, rows):
    problems = rules.validate(rows, brief["languages"])
    path = os.path.join(args.out, "review.md")
    with open(path, "w", encoding="utf-8") as f:
        f.write(f"# Review: new products for {brief['shop']['name']}\n\n")
        f.write(f"{len(rows)} rows · {len(brief['languages'])} languages · "
                + ("**ready to finalize**" if not problems else f"**{len(problems)} problem(s) to fix**") + "\n\n")
        if problems:
            f.write("## Problems\n\n" + "\n".join(f"- [ ] {p}" for p in problems) + "\n\n")
        f.write("## Read before approving\n\n")
        f.write("The rules check prices, margins, length, banned claims and coverage. "
                "Facts, tone and translations are yours to check.\n\n")
        f.write("| SKU | Lang | Product | Price | Description |\n| --- | --- | --- | --- | --- |\n")
        for r in rows:
            f.write(f"| {r['sku']} | {r['lang']} | {r['name']} | €{r['price_eur']} | {r['description'].replace('|', '/')} |\n")
    print(f"Wrote {path}: " + ("no problems" if not problems else f"{len(problems)} problem(s)"))
    return problems


def write_csv(path, rows, columns):
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=columns, extrasaction="ignore")
        w.writeheader()
        w.writerows(rows)


def read_csv(path):
    if not os.path.exists(path):
        sys.exit(f"{path} not found: run 'draft' first")
    with open(path, newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    for name in ("draft", "validate", "finalize"):
        p = sub.add_parser(name)
        p.add_argument("--brief", required=True)
        p.add_argument("--out", required=True)
        if name == "draft":
            p.add_argument("--mock", action="store_true", help="use recorded model responses, no API key needed")
        if name == "finalize":
            p.add_argument("--approved-by", required=True)
    args = ap.parse_args()
    {"draft": draft, "validate": validate, "finalize": finalize}[args.cmd](args)


if __name__ == "__main__":
    main()
