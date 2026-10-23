# Palette's UX Journal

## 2026-07-06 - Telegram Mini App Accessibility Baseline
**Learning:** Telegram Mini App single-page HTML interfaces require explicit ARIA attributes (`aria-label` on icon buttons, `aria-expanded` on collapsible content toggles, `role="tab"` / `aria-selected` on tab bar) and `:focus-visible` ring styles to ensure accessibility for screen readers and keyboard users in Telegram WebApp views.
**Action:** Always include accessibility semantics (`aria-*` attributes and `:focus-visible` styles) when updating Mini App frontend components.
