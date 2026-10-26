## 2025-02-18 - Mini App Accessibility Standards
**Learning:** Telegram Mini App Web Views lack default focus-visible indicators and accessible names for emoji/icon-only buttons (`✏️`, `✕`), impairing screen reader and keyboard navigation.
**Action:** Always provide explicit `aria-label` attributes on icon-only buttons, dynamic `aria-expanded` states on collapsible panels, `role="status"` on toast elements, and explicit `:focus-visible` CSS outlines.
