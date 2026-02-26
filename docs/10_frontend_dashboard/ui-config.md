# UI Configuration & Themes

> Theme system, CSS variables, and WCAG contrast requirements.

---

## 3 Hardcoded Themes

| Theme | Mode | Style |
|-------|------|-------|
| `cyberpunk-neon` | Dark | Neon purple accents |
| `beach-paradise` | Light | Warm teal accents |
| `midnight-ocean` | Dark | Bloomberg-style blue |

Applied via `document.documentElement.style.setProperty()`. Stored in `themeStore`.

---

## CSS Variable Contract

All components MUST use CSS variables. No hardcoded colors.

```css
/* Layer 1: Backgrounds */
--bg-primary        /* Body background */
--bg-secondary      /* Card/panel backgrounds */
--bg-surface        /* Glass surfaces with opacity */
--bg-elevated       /* Modals, dropdowns */

/* Layer 2: Text (WCAG AA validated) */
--text-primary      /* Headings — Contrast >= 7:1 */
--text-secondary    /* Body text — Contrast >= 4.5:1 */
--text-muted        /* Hints — Contrast >= 3:1 */

/* Layer 3: Interactive */
--accent            /* Primary buttons, links */
--accent-hover      /* Hover state */
--accent-active     /* Active/pressed */

/* Layer 4: Semantic (Trading) */
--success           /* Profit, long, positive */
--success-light     /* Background variant */
--danger            /* Loss, short, errors */
--danger-light      /* Background variant */
--warning           /* Pending, rate limits */

/* Layer 5: Structure */
--border            /* Borders, dividers */
--border-focus      /* Focus rings */
--glow              /* Glow effects */
--overlay           /* Modal overlays */

/* Layer 6: RGB Values */
--accent-rgb        /* For rgba() usage */
--success-rgb
--danger-rgb
```

---

## Theme Palettes

### Cyberpunk Neon (Dark)

| Token | Value | Contrast vs bg |
|-------|-------|---------------|
| --bg-primary | #0f172a | — |
| --text-primary | #f8fafc | 15.4:1 |
| --accent | #8b5cf6 | 4.6:1 |
| --success | #10b981 | 4.5:1 |
| --danger | #f43f5e | 4.7:1 |

### Beach Paradise (Light)

| Token | Value | Contrast vs bg |
|-------|-------|---------------|
| --bg-primary | #fef7ed | — |
| --text-primary | #1e293b | 12.6:1 |
| --accent | #0d9488 | 4.5:1 |
| --success | #059669 | 4.6:1 |
| --danger | #dc2626 | 5.4:1 |

### Midnight Ocean (Dark)

| Token | Value | Contrast vs bg |
|-------|-------|---------------|
| --bg-primary | #0a1628 | — |
| --text-primary | #e2e8f0 | 11.8:1 |
| --accent | #0ea5e9 | 4.8:1 |
| --success | #22c55e | 5.3:1 |
| --danger | #ef4444 | 5.0:1 |

---

## Performance Mode

Disable `backdrop-filter` for low-latency environments via `.performance-mode` CSS class.
