Translate these product descriptions from English into {language_name} ({lang}) for an online shop.

<items>
{items}
</items>

Rules:
- Return only JSON: a list of objects with the keys "sku" and "description".
- Keep every SKU unchanged and include each one exactly once.
- Keep the friendly tone; adapt idioms instead of translating word for word.
- At most {max_chars} characters per description.
- Keep product names, units and origins (e.g. "Kenya Kiambu", "600 ml") as they are.
