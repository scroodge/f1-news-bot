## 2026-07-06 - Accessible form labels and icon buttons in Mini App dynamic templates
**Learning:** Dynamic HTML template cards generated via JS in single-file Mini Apps often lack explicitly tied labels (`for`/`id`) and missing ARIA labels on icon-only buttons like `✕` and `✏️`.
**Action:** Always append item IDs to form element `id` and label `for` attributes when dynamically rendering forms, and add explicit `aria-label`s in Belarusian to icon-only buttons.
