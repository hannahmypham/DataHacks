---
name: ui-ux-snaptrash
description: Applies the global UI/UX Pro Max skill (67 styles, palettes, charts, shadcn/ui, Tailwind) + Framer Motion animations + 21st.dev magic components to the SnapTrash React dashboard. Use for all frontend work in apps/frontend/, designing the scan screen, two-column results cards (food/plastic with severity badges), weekly trends/forecast charts (Recharts + Framer Motion), Mapbox choropleth, gamification popups, accessibility, dark mode, bento-style layouts, and responsive mobile camera upload. Follows the exact screens from snaptrash-plan.md and DETAILED-OVERVIEW.md.
---

# UI/UX Pro Max for SnapTrash Dashboard

This skill integrates the global **ui-ux-pro-max**, **website-builder-setup** (Framer Motion + 21st.dev), and shadcn/ui patterns specifically for the SnapTrash frontend (`apps/frontend/`).

**Frontend Stack** (already set up):
- React 18 + Vite + TypeScript + Tailwind + Recharts + Framer Motion (already in package.json).
- shadcn/ui style (clsx, cva, tailwind-merge, lucide-react icons).
- Components for camera upload, results cards, charts, Mapbox map, confetti/gamification.

## When to Use
- Any change to `apps/frontend/src/` (App.tsx, components, api.ts).
- Designing scan/results/weekly/map screens from the plan.
- Adding animations (Framer Motion), charts, color-coded severity (⚠️ BANNED, ✅ Recyclable), percentile badges.
- Accessibility, responsive design, dark mode, hover states, loading spinners.

## SnapTrash-Specific UI Rules (from plan + overview)
- **Results Screen**: Two-column layout (🥦 FOOD WASTE | 🧴 PLASTIC). Color-coded badges (green/red/yellow). Food: type, shelf life, compost/contaminated, $ wasted, CO2. Plastic: polymer, status (banned_CA), alert text. No manufacturer references.
- **SCAN SCREEN**: Prominent 📷 "Snap Bin" button → camera preview → upload with loading spinner.
- **WEEKLY DASHBOARD**: Recharts line chart (waste_kg + dotted forecast), donut breakdowns, stat cards ($ wasted | CO2 | harmful plastics), percentile popup with confetti (Framer Motion).
- **MAP VIEW**: Mapbox choropleth (San Diego neighborhoods colored by plastic intensity), pinned restaurant, tooltips like "North Park: 1.8t PET 🟡 approaching threshold".
- **Style Priorities** (UI/UX Pro Max):
  - Accessibility (CRITICAL): 4.5:1 contrast, ARIA labels, keyboard nav, reduced-motion respect.
  - Modern minimalism or bento grid for dashboard.
  - Tailwind + shadcn/ui components (cards, badges, tables, charts).
  - Framer Motion: Smooth page transitions, hover scales, scroll reveals on results, confetti animation on high percentile.
  - Color palette: Green (compostable/success), red (contaminated/banned), amber (warnings), dark mode default.
  - Typography: Clean sans-serif pairings; readable on mobile.
  - Responsive: Mobile-first camera experience.

## Recommended Patterns
- Use functional components + custom hooks (`src/lib/`).
- Colocate Framer Motion variants with components.
- Leverage 21st.dev/shadcn for polished cards, modals, charts.
- Poll API with React Query or SWR; show skeleton loaders (Framer).
- Gamification: Framer-animated confetti + badge on "better than X%".

## Integration with Global Skills
- **UI/UX Pro Max**: Apply its 67 styles, 96 palettes, 57 font pairings, 25 chart types when generating/reviewing components. Prioritize accessibility (priority 1), touch targets, performance.
- **Framer Motion**: All animations must use it (from website-builder-setup).
- **21st.dev Magic**: Pull production-ready React components for dashboard elements.

**Example Prompt for Grok**: "Using ui-ux-snaptrash skill, redesign the results screen with Framer Motion animations and a bento layout while keeping the exact two-column food/plastic structure from the plan."

Always update `DETAILED-OVERVIEW.md` screenshots/descriptions if UI changes. Combine with `snaptrash` skill for data binding (food/plastic JSON from API).

This ensures the SnapTrash dashboard is beautiful, accessible, animated, and true to the original vision.
