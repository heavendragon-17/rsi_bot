# Frontend Contribution Guidelines

The authoritative frontend architecture is
[`docs/10_frontend_dashboard/`](../../docs/10_frontend_dashboard/). These
rules supplement that documentation:

- Use existing components and design tokens before introducing new variants.
- Keep API access in `ui/src/api/` and shared state in the relevant Zustand
  store; presentation components should not construct backend URLs.
- Preserve responsive behavior across narrow mobile, tablet, and desktop
  layouts.
- Every interactive control needs a visible label or accessible name, keyboard
  operation, and a clear disabled/loading state.
- Use explicit TypeScript types. Do not add `@ts-nocheck` or broaden values to
  `any` to suppress an integration error.
- Run `npm run type-check` and `npm run build` before committing.
- Update `docs/10_frontend_dashboard/` when behavior, routes, stores, or design
  tokens change.

Historical task checklists in this directory are retained only for design
provenance.
