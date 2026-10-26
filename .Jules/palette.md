## 2025-02-18 - Mini App Accessibility Standards
**Learning:** Telegram Mini App Web Views lack default focus-visible indicators and accessible names for emoji/icon-only buttons (`✏️`, `✕`), impairing screen reader and keyboard navigation.
**Action:** Always provide explicit `aria-label` attributes on icon-only buttons, dynamic `aria-expanded` states on collapsible panels, `role="status"` on toast elements, and explicit `:focus-visible` CSS outlines.
## 2026-07-06 - Accessible form labels and icon buttons in Mini App dynamic templates
**Learning:** Dynamic HTML template cards generated via JS in single-file Mini Apps often lack explicitly tied labels (`for`/`id`) and missing ARIA labels on icon-only buttons like `✕` and `✏️`.
**Action:** Always append item IDs to form element `id` and label `for` attributes when dynamically rendering forms, and add explicit `aria-label`s in Belarusian to icon-only buttons.
