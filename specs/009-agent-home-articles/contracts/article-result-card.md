# Article Result Card Contract

## Input

An owned Agent task result may contain one or more article objects with:

- `id`: article identifier
- `title`: human-readable title
- `link`: private article detail path
- optional `category` and `tags`

## Presentation guarantees

- Render one interactive card per valid article.
- Use `link` only when it targets the application's private article detail route.
- Never render an internal ID as the user-facing label.
- Omit missing metadata rather than rendering placeholders.
- Empty or malformed results produce no card section and retain the textual fallback.
