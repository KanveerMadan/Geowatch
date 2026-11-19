# Merge notes (build/product)

This branch merges LAST, after the flood and change branches. Every file
outside the new product/deploy files that this branch changes is listed here
with the reason.

| File | Change | Why |
|---|---|---|
| web/src/main.jsx | Rewritten as a router (route.js): landing / explore / gallery / honesty / report, each lazy | New public pages. If a branch edits main.jsx, keep its change inside the `explore` (App) or `report` route |
| web/src/design/tokens.js | Added `type.hero` only | Landing headline (D3) |
| web/index.html | Added a meta description | SEO / link previews |
