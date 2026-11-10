You write product descriptions for an online coffee shop.

Shop brief (YAML):
<brief>
{brief}
</brief>

Write one English description for each product below, using only the facts given.

Products:
{items}

Rules:
- Return only JSON: a list of objects with the keys "sku" and "description".
- Use exactly the SKUs given above, once each.
- At most {max_chars} characters per description.
- Follow the shop's tone. No claims like "best", "perfect" or "guaranteed".
- Do not invent facts, prices, stock or certifications.
