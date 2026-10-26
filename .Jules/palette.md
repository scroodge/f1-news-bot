# Palette's UX Journal

## 2026-07-06 - Telegram Mini App Accessibility Baseline
**Learning:** Telegram Mini App single-page HTML interfaces require explicit ARIA attributes (`aria-label` on icon buttons, `aria-expanded` on collapsible content toggles, `role="tab"` / `aria-selected` on tab bar) and `:focus-visible` ring styles to ensure accessibility for screen readers and keyboard users in Telegram WebApp views.
**Action:** Always include accessibility semantics (`aria-*` attributes and `:focus-visible` styles) when updating Mini App frontend components.
## 2026-07-06 - Telegram Mini App Icon Buttons Accessibility
**Learning:** Icon-only buttons (like `✕` for reject and `✏️` for edit) and dynamic feedback overlays (like toast notifications and tabs) in single-file webapps lack screen reader accessibility unless explicitly annotated with ARIA attributes (`aria-label`, `role="status"`, `role="tab"`).
**Action:** Always provide explicit `aria-label` and `title` attributes on icon-only control buttons, and set `aria-live="polite"` on notification toasts in web view components.
## 2025-02-18 - Mini App Accessibility Standards
**Learning:** Telegram Mini App Web Views lack default focus-visible indicators and accessible names for emoji/icon-only buttons (`✏️`, `✕`), impairing screen reader and keyboard navigation.
**Action:** Always provide explicit `aria-label` attributes on icon-only buttons, dynamic `aria-expanded` states on collapsible panels, `role="status"` on toast elements, and explicit `:focus-visible` CSS outlines.
