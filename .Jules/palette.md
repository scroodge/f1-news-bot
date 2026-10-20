## 2026-07-06 - Telegram Mini App Icon Buttons Accessibility
**Learning:** Icon-only buttons (like `✕` for reject and `✏️` for edit) and dynamic feedback overlays (like toast notifications and tabs) in single-file webapps lack screen reader accessibility unless explicitly annotated with ARIA attributes (`aria-label`, `role="status"`, `role="tab"`).
**Action:** Always provide explicit `aria-label` and `title` attributes on icon-only control buttons, and set `aria-live="polite"` on notification toasts in web view components.
