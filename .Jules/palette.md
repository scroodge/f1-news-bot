# Palette's Journal

## 2026-07-06 - Telegram Mini App Accessibility
**Learning:** Icon-only buttons (like `✕` reject and `✏️` edit) and form fields in Telegram Mini App interfaces often lack explicit ARIA labels and label/input associations, which degrades screen reader usability and keyboard navigation.
**Action:** Always provide explicit `aria-label` attributes for icon-only controls, `:focus-visible` ring indicators for keyboard users, and link form `<label>` elements to input `id`s using `for` in dynamic WebApp HTML cards.
