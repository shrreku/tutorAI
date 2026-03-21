# StudyAgent — Scholar Theme Visual Asset Plan

> Direction document for icons, illustrations, animations, and visual assets that complement the Scholar (v1) theme. **No assets are created here** — this is the brief for future production.

---

## 1. Design Language Summary

| Token | Value |
|---|---|
| **Palette** | Warm ivory background (`#FAF8F5`), walnut sidebar (`#3E3428`), sage green accent (`#6B8F71`), muted foreground (`#5C5347`) |
| **Typography** | Newsreader (serif, display/headings), Source Sans 3 (sans-serif, body) |
| **Radius** | `rounded-lg` / `rounded-xl` (8–12 px) — no pill-shaped containers except badges |
| **Shadows** | Minimal; prefer `border` over `box-shadow`. No colored glow effects |
| **Mood** | Warm, scholarly, paper-like. Think open textbook on a wooden desk, not neon SaaS dashboard |

---

## 2. Iconography

### 2a. Style Direction
- **Line weight:** 1.5 px stroke, matching Lucide's default
- **Corner radius:** Rounded caps and joins (consistent with Lucide)
- **Color:** Single-tone — use `text-gold` (sage green), `text-muted-foreground`, or `text-foreground` only
- **Size grid:** 16 px (inline), 20 px (card headers), 24 px (empty states), 40 px (hero)

### 2b. Custom Icons Needed
These are domain-specific icons not available in Lucide that would strengthen the learning platform feel:

| Icon | Where Used | Description |
|---|---|---|
| **Notebook** | Sidebar, cards | Open notebook with a bookmark ribbon — distinguish from generic `BookOpen` |
| **Study lamp** | Empty states | Desk lamp casting warm light — conveys "study time" |
| **Mastery gauge** | Progress sections | Semi-circular gauge with a needle — more evocative than a progress bar |
| **Concept node** | Mastery map | Small interconnected circles — represents concept relationships |
| **Tutor avatar** | Chat bubbles | Minimalist owl or mortarboard silhouette — gives the tutor a persona |
| **Artifact scroll** | Artifact panel | Rolled parchment with a wax seal — distinguishes generated outputs |
| **Checkpoint flag** | Checkpoint cards | Small pennant flag — marks understanding checks |

### 2c. Production Notes
- Export as SVG, optimized with SVGO
- Provide both outline and filled variants
- Package as a local icon component library (e.g. `src/components/icons/`) so they can be imported like Lucide icons
- Ensure all icons pass WCAG AA contrast against both `--background` and `--card` surfaces

---

## 3. Illustrations

### 3a. Style Direction
- **Technique:** Flat line-art with selective watercolor-wash fills
- **Palette:** Constrained to theme colors — ivory, walnut brown, sage green, warm gray. No bright saturated colors
- **Line:** Same 1.5 px weight as icons; hand-drawn feel without being cartoonish
- **Composition:** Centered, simple subjects with generous negative space. No busy backgrounds
- **Aspect ratios:** 4:3 for cards, 16:9 for hero/banner, 1:1 for empty states

### 3b. Illustration Set Needed

| Illustration | Location | Subject |
|---|---|---|
| **Hero — open desk** | Landing page hero | Bird's-eye view of a wooden desk with an open notebook, a pen, and a coffee cup. Warm, inviting. |
| **Empty notebook** | Notebooks page (0 state) | Single closed notebook with a subtle "+" symbol. Encourages creation. |
| **No resources** | Resources empty state | Stack of blank pages with a dashed outline where a file would go. |
| **Session start** | Study workspace empty state | Tutor owl perched on the edge of an open book, looking expectant. |
| **Artifact ready** | Artifact panel success | Small scroll unfurling with sparkle marks. |
| **Mastery celebration** | Progress milestone | Open notebook with a small laurel wreath. Understated but rewarding. |
| **Auth side panel** | Login/Register left panel | Full-height: a library shelf fading into warm light. Sets academic tone. |
| **404 / Error** | Error pages | Closed book with a question mark bookmark. |

### 3c. Production Notes
- Export as SVG for scalability; provide PNG fallbacks at 1× and 2× for email/social
- Each illustration should have a transparent background variant
- Keep file size under 15 KB per SVG (optimize paths)
- Consider providing a Lottie-compatible version for the hero illustration (see §4)

---

## 4. Animations & Micro-interactions

### 4a. Principles
- **Purposeful:** Every animation should communicate state change or draw attention to important content. No decorative animation.
- **Subtle:** Durations 150–300 ms for UI transitions, 600–1200 ms for illustration reveals
- **Easing:** `ease-out` for entrances, `ease-in` for exits. Use CSS `cubic-bezier(0.16, 1, 0.3, 1)` for spring-like entrances
- **Reduced motion:** All animations must respect `prefers-reduced-motion: reduce`

### 4b. Specific Animations

| Animation | Trigger | Duration | Description |
|---|---|---|---|
| **fade-up** | Page/card mount | 400 ms | Already exists. Elements translate up 8 px and fade in. Keep as-is. |
| **tab-enter** | Tab switch | 200 ms | Quick opacity fade for tab content swap. Already exists. |
| **mastery-bar fill** | Progress update | 600 ms | Bar width animates from 0 to target %. Add `transition-all duration-600 ease-out`. |
| **checkpoint slide-in** | Checkpoint event | 300 ms | Checkpoint card slides in from below with a subtle border pulse. |
| **artifact shimmer** | Artifact generating | Loop | Subtle pulsing opacity on the generating indicator. Use `animate-pulse`. |
| **hero desk scene** | Landing page load | 1200 ms | (Future) Lottie animation: pen writes a line, lamp flickers on. Optional enhancement. |
| **tutor typing** | Tutor thinking | Loop | Three-dot bounce or pulsing Sparkles icon. Currently uses `animate-spin` on Loader2 — consider switching to a gentler pulse. |
| **scroll-to-bottom** | New message | 300 ms | Smooth scroll with `behavior: 'smooth'`. Already implemented. |

### 4c. Implementation Notes
- Use CSS animations / Tailwind `animate-*` utilities for simple transitions
- Use Framer Motion for layout animations (list reorder, panel open/close) if added later
- Use Lottie (`lottie-react`) only for the hero illustration; keep it optional and lazy-loaded
- All animation classes should be defined in `index.css` under `@layer utilities`

---

## 5. Favicon & Brand Mark

| Asset | Spec | Description |
|---|---|---|
| **Favicon** | 32×32 px, SVG + ICO | Sage green circle with a white open-book silhouette |
| **Apple touch icon** | 180×180 px, PNG | Same mark on ivory background with rounded corners |
| **OG image** | 1200×630 px, PNG | Hero desk illustration with "StudyAgent" wordmark in Newsreader, sage green accent bar |
| **Logo wordmark** | SVG | "StudyAgent" in Newsreader semibold, with the small book icon preceding it |

---

## 6. File Organization

```
frontend/
  public/
    favicon.svg
    favicon.ico
    apple-touch-icon.png
    og-image.png
  src/
    assets/
      illustrations/
        hero-desk.svg
        empty-notebook.svg
        no-resources.svg
        session-start.svg
        artifact-ready.svg
        mastery-celebration.svg
        auth-library.svg
        error-404.svg
      icons/
        notebook.svg
        study-lamp.svg
        mastery-gauge.svg
        concept-node.svg
        tutor-avatar.svg
        artifact-scroll.svg
        checkpoint-flag.svg
    components/
      icons/
        index.ts          // re-exports all custom icons as React components
        Notebook.tsx
        StudyLamp.tsx
        ...
```

---

## 7. Priority & Phasing

### Phase 1 — Immediate (ship with Scholar theme)
- Custom **favicon** and **apple-touch-icon** (replace default Vite icon)
- **OG image** for link previews
- **Auth side panel** illustration (high-visibility, sets first impression)

### Phase 2 — Near-term (next sprint)
- All **empty state illustrations** (notebook, resources, session, artifact, error)
- Custom **notebook icon** and **tutor avatar icon** for sidebar and chat
- **Mastery bar fill** animation polish

### Phase 3 — Enhancement (backlog)
- Full custom icon set (7 icons)
- **Hero desk Lottie** animation for landing page
- **Checkpoint slide-in** and other micro-interaction refinements
- Seasonal or event-based illustration variants (exam season, welcome back)

---

## 8. Design Tool Recommendations

- **Figma** for icon and illustration design (export SVG directly)
- **SVGO** for SVG optimization (`npx svgo -f src/assets/`)
- **Lottie / Bodymovin** for complex animations (After Effects → JSON)
- **realfavicongenerator.net** for favicon set generation from a single SVG source
