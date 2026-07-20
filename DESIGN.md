# Chillify Design Contract

## Direction

**Focused. Familiar. Luminous.**

Spotify Web Player supplies the interaction-density reference, Plexamp supplies collection craft, and YouTube Music supplies legible media hierarchy. Chillify uses original wording, iconography, assets, and proportions.

The deliberate signature is the **listening glow**: only active media and acquisition progress receive the emerald `color.accent` signal, producing a restrained luminous edge on the current cover, active navigation marker, and real progress rail. Static containers stay neutral. This makes “playing or moving toward playable” visually unmistakable without decorative gradients.

V1 is a forced dark interface. A light token set is not applicable to this milestone.

## Token source and handoff

Before Task 0, the token tables below are the single source of exact values. Task 0 emits the same values and computed contrast notes to `frontend/src/styles/tokens.css`; at that point the code file becomes the single source, exact values/ratios are removed from this document, and this document retains role and usage rules by token name only. Components never contain raw color, length, font, shadow, duration, or easing values.

### Color tokens — dark

| Token | Value | Role |
|---|---|---|
| `color.background` | `#000000` | browser canvas, sidebar, player perimeter |
| `color.surface` | `#121212` | primary content viewport |
| `color.surface-raised` | `#181818` | dialogs, sheets, menus, elevated cards |
| `color.surface-hover` | `#242424` | hover and pressed-neutral surface |
| `color.surface-selected` | `#2E2E2E` | selected row, active tab background |
| `color.foreground` | `#FFFFFF` | primary text and high-emphasis icons |
| `color.foreground-muted` | `#B3B3B3` | secondary metadata and inactive controls |
| `color.foreground-subtle` | `#9A9A9A` | timestamps, tertiary metadata, disabled labels |
| `color.accent` | `#2EE59D` | listening glow, primary action, real progress |
| `color.accent-foreground` | `#06140E` | text/icons on accent |
| `color.destructive` | `#FF6B73` | destructive action and error text |
| `color.destructive-foreground` | `#190204` | text/icons on destructive fill |
| `color.warning` | `#F6C85F` | degraded/attention signal |
| `color.warning-foreground` | `#1A1200` | text/icons on warning fill |
| `color.info` | `#79C7FF` | internet/provider provenance and informational state |
| `color.info-foreground` | `#001521` | text/icons on info fill |
| `color.border` | `#333333` | separators, quiet outlines, input boundary |
| `color.focus` | `#8BD5FF` | focus-visible ring |
| `color.progress-track` | `#4D4D4D` | inactive seek/progress rail |
| `color.cover-placeholder` | `#282828` | missing artwork field |
| `color.overlay` | `#000000` | dialog/sheet overlay base |
| `opacity.overlay` | `0.72` | dialog/sheet overlay opacity |
| `opacity.disabled` | `0.48` | disabled control opacity |

### Text and UI contrast

| Pair | FG | BG | Contrast | Usage |
|---|---|---|---|---|
| Canvas primary | `color.foreground` | `color.background` | `21.00:1` | shell/player text |
| Surface primary | `color.foreground` | `color.surface` | `18.73:1` | page text |
| Raised primary | `color.foreground` | `color.surface-raised` | `17.76:1` | dialog/menu text |
| Hover primary | `color.foreground` | `color.surface-hover` | `15.52:1` | hovered rows |
| Selected primary | `color.foreground` | `color.surface-selected` | `13.58:1` | selected navigation/rows |
| Canvas secondary | `color.foreground-muted` | `color.background` | `10.02:1` | player metadata |
| Surface secondary | `color.foreground-muted` | `color.surface` | `8.93:1` | track metadata |
| Raised secondary | `color.foreground-muted` | `color.surface-raised` | `8.47:1` | dialog help |
| Hover secondary | `color.foreground-muted` | `color.surface-hover` | `7.40:1` | row metadata |
| Surface tertiary | `color.foreground-subtle` | `color.surface` | `6.66:1` | timestamps |
| Raised tertiary | `color.foreground-subtle` | `color.surface-raised` | `6.31:1` | diagnostics metadata |
| Hover tertiary | `color.foreground-subtle` | `color.surface-hover` | `5.52:1` | quiet hovered metadata |
| Selected tertiary | `color.foreground-subtle` | `color.surface-selected` | `4.83:1` | disabled selected metadata |
| Canvas tertiary | `color.foreground-subtle` | `color.background` | `7.46:1` | quiet player timestamps |
| Accent fill | `color.accent-foreground` | `color.accent` | `11.50:1` | primary button/badge |
| Destructive fill | `color.destructive-foreground` | `color.destructive` | `7.23:1` | confirmed destructive button |
| Destructive text | `color.destructive` | `color.surface` | `6.78:1` | inline error |
| Warning fill | `color.warning-foreground` | `color.warning` | `11.81:1` | degraded badge |
| Warning text | `color.warning` | `color.surface` | `11.91:1` | persistent degraded alert |
| Info fill | `color.info-foreground` | `color.info` | `10.12:1` | internet-source badge |
| Info text | `color.info` | `color.surface` | `10.19:1` | provider status |
| Focus on canvas | `color.focus` | `color.background` | `13.06:1` | focus indicator |
| Focus on surface | `color.focus` | `color.surface` | `11.65:1` | focus indicator |
| Focus on raised | `color.focus` | `color.surface-raised` | `11.04:1` | focus indicator |
| Focus on hover | `color.focus` | `color.surface-hover` | `9.65:1` | focus indicator |
| Focus on selected | `color.focus` | `color.surface-selected` | `8.44:1` | focus indicator |

### Typography tokens

| Token | Value | Usage |
|---|---|---|
| `font.sans` | `system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif` | all product text |
| `font.mono` | `ui-monospace, "SFMono-Regular", Consolas, monospace` | technical details only |
| `type.display` | `2rem / 2.5rem / 700` | profile chooser and context identity |
| `type.title` | `1.5rem / 2rem / 700` | page headings |
| `type.section` | `1.125rem / 1.5rem / 700` | section and dialog headings |
| `type.body` | `0.9375rem / 1.375rem / 400` | body and form copy |
| `type.label` | `0.875rem / 1.25rem / 600` | controls and track title |
| `type.meta` | `0.8125rem / 1.125rem / 400` | metadata, badges, timestamps |
| `type.micro` | `0.75rem / 1rem / 600` | progress phase and compact status |

### Space, size, radius, shadow, and motion tokens

| Token | Value | Usage |
|---|---|---|
| `space.0` | `0` | reset |
| `space.1` | `0.25rem` | tight icon/text gap |
| `space.2` | `0.5rem` | compact control gap |
| `space.3` | `0.75rem` | row internal gap |
| `space.4` | `1rem` | standard component padding |
| `space.5` | `1.5rem` | section padding |
| `space.6` | `2rem` | page rhythm |
| `space.8` | `3rem` | major section separation |
| `size.control-sm` | `2rem` | compact row/icon control |
| `size.control` | `2.5rem` | standard interactive control |
| `size.control-lg` | `3rem` | primary player/profile action |
| `size.row` | `3.5rem` | dense track/download row |
| `size.cover-sm` | `2.5rem` | row artwork |
| `size.cover-md` | `5rem` | player/context compact artwork |
| `size.cover-lg` | `14rem` | album/context artwork |
| `layout.sidebar` | `15rem` | desktop sidebar |
| `layout.topbar` | `4rem` | sticky top bar |
| `layout.player` | `5.5rem` | persistent player |
| `layout.content-max` | `100rem` | readable wide-screen cap |
| `breakpoint.desktop` | `64rem` | release-target desktop shell |
| `breakpoint.wide` | `90rem` | expanded context grid |
| `radius.sm` | `0.25rem` | badges, compact fields |
| `radius.md` | `0.5rem` | inputs, menus, rows |
| `radius.lg` | `0.75rem` | dialogs, sheets, artwork |
| `radius.pill` | `9999px` | primary play and status pills |
| `shadow.raised` | `0 0.75rem 2.5rem rgb(0 0 0 / 0.45)` | menus, dialogs, sheets |
| `shadow.listening` | `0 0 0 0.125rem rgb(46 229 157 / 0.72), 0 0.5rem 1.5rem rgb(46 229 157 / 0.16)` | current artwork only |
| `motion.fast` | `120ms` | hover/focus/color |
| `motion.standard` | `180ms` | menus, tooltips, row state |
| `motion.deliberate` | `240ms` | dialog/sheet enter/exit |
| `ease.standard` | `cubic-bezier(0.2, 0, 0, 1)` | normal state transition |
| `ease.exit` | `cubic-bezier(0.4, 0, 1, 1)` | leaving state |

Spacing follows the `space.*` scale, whose token table encodes the approved compact grid. Component dimensions use `size.*` and layout dimensions use `layout.*`; feature code does not create one-off values.

## Shadcn adoption map

| UX need | Required Shadcn source | Composition rule |
|---|---|---|
| Application navigation | Sidebar, NavigationMenu, DropdownMenu, Button, Badge, Tooltip | one stable shell; active state uses selected tokens |
| Track/download lists | Table, Button, DropdownMenu, Badge, Progress, Skeleton, Tooltip | domain rows remain dense and keyboard operable |
| Search/forms/settings | Field, FieldGroup, Label, Input, Select, Switch, Button, Alert | FieldError owns field failure; Alert owns durable failure |
| Browse modes | Tabs, Card, AspectRatio, ScrollArea, Separator | cards are reserved for media contexts, not generic dashboards |
| Dialog workflows | Dialog, AlertDialog, Sheet, Button, Field, Alert | visible title/description, trapped focus, invoking-control return |
| Player | Button, Slider, Tooltip, AspectRatio | audio behavior stays in player domain store/controller |
| Feedback | Sonner, Alert, Progress, Badge, Empty, Skeleton | toast for brief acknowledgement; persistent state stays inline |
| Disclosure | Accordion, DropdownMenu, Tooltip | technical detail stays opt-in and redacted |
| Reordering | Shadcn visual rows/buttons plus dnd-kit behavior | keyboard and pointer paths have equal capability |

There are no unapproved primitive gaps. `TrackRow`, `ContextGrid`, `ArtworkPicker`, `GlobalJobIndicator`, `PersistentPlayer`, and sortable playlist/queue rows are domain compositions of the mapped Shadcn sources. Browser audio control and dnd-kit sorting are nonvisual behavior already assigned by ARCHITECTURE.

## Interactive component states

| Element | Default | Hover | Focus-visible | Active/selected | Disabled |
|---|---|---|---|---|---|
| Primary button | accent fill and accent foreground | preserve contrast; raise emphasis without glow spread | focus token ring outside edge | compressed visual state; no layout shift | disabled opacity; no pointer action |
| Secondary/icon button | transparent or raised-neutral with foreground-muted | surface-hover and foreground | focus token ring | surface-selected and foreground | disabled opacity; tooltip explains unavailable action when useful |
| Sidebar/nav/link | foreground-muted on background | foreground on surface-hover | focus token ring | foreground, surface-selected, accent marker | disabled opacity and no navigation |
| Track/download row | transparent on surface | surface-hover | row/action focus ring follows reading order | surface-selected; current media adds listening glow to cover only | unavailable row keeps readable metadata and disables Play |
| Media/context card | surface-raised | surface-hover with raised shadow | focus token ring around card action | selected surface; playing cover uses listening glow | disabled opacity only when entire context is unavailable |
| Input/select | surface-raised, border, foreground | stronger border token | focus token ring and visible label | unchanged geometry | disabled opacity and preserved label |
| Switch/tab | neutral track or inactive foreground | surface-hover | focus token ring | accent signal with accent foreground where filled | disabled opacity |
| Slider/progress | progress-track with foreground thumb for editable control | thumb emphasis | focus token ring around thumb/rail | accent filled range; determinate only from real values | disabled opacity; noneditable Progress has no thumb |
| Menu item | foreground on surface-raised | surface-hover | focus token ring/inset selected surface | closes after committed action | disabled opacity with optional reason |
| Dialog/sheet/alert dialog | raised surface and overlay | actions follow button rules | initial focus follows safety rule; focus remains contained | destructive confirmation uses destructive tokens | submit disabled during validation/mutation |
| Drag handle | foreground-muted icon button | foreground on surface-hover | focus token ring | selected row follows movement with announced position | disabled until complete ordered data loads |
| Toast/dismiss | raised surface with semantic text | dismiss button surface-hover | dismiss focus ring | exits after acknowledgement | no disabled state |

No hover-only capability exists. Reduced-motion mode removes translation/scale and uses immediate or `motion.fast` opacity/color feedback.

## Data-view states

| View family | Screens | Empty | Loading | Error/degraded |
|---|---|---|---|---|
| Profiles | S1 | creation Field is primary and focused | fixed profile Skeletons; duplicate action disabled | inline FieldError preserves name |
| Library/search | S2, S3 | Empty explains managed-download/local-first behavior and next action | fixed row Skeletons; local content remains usable during online load | Alert/inline provider state stays scoped; remote and local regions never merge |
| Contexts | S6, S7, S8 | Empty explains absent playable tracks/Unknown correction | identity geometry and player remain stable | local Retry affects viewport only; unavailable rows remain labeled |
| Playlists | S9, S10 | Empty routes to Create or Add from Library | header remains; reorder disabled until complete | restore last confirmed order and show inline retry |
| Downloads | S11 | Empty states background independence and acquisition entry | retain last known rows and mark stale while reconnecting | persistent Alert for Redis; row Alert/Accordion for retryable detail |
| Settings | S12 | seeded provider/storage cards always exist | each health result loads independently | proxy/provider/storage failure is isolated and actionable |
| Editors | S4, S5, S13, S16 | required fields and supported scope are explicit | dialog geometry remains; commit action disabled | FieldError preserves edits; old durable version remains visible |
| Queue | S14 | Empty explains how contexts create a queue | browser-local; no server loading skeleton | missing items label/skip; playback error advances or stops |
| Delete | S15 | not applicable after impact resolves missing track | impact Skeleton blocks confirmation | dialog remains open; recovery prevents duplicate mutation |

Skeletons match final row/card geometry. Spinners are reserved for compact actions without predictable content shape. Determinate progress appears only for real reported percentages; phase text and elapsed state serve indeterminate work.

## Layout and density

- At and above `breakpoint.desktop`, the fixed `layout.sidebar`, sticky `layout.topbar`, scrollable content viewport, and fixed `layout.player` form the persistent shell. Only the route outlet scrolls vertically.
- Below `breakpoint.desktop`, the sidebar becomes a Shadcn Sheet and controls may wrap; this is functional fallback, not the deferred mobile experience.
- Content uses `space.5` edge padding and is capped by `layout.content-max`; context grids expand at `breakpoint.wide`.
- Track/download rows use `size.row` and `size.cover-sm`. Primary row identity gets the first readable column; source/status, duration, and actions remain aligned and do not become detached cards.
- Dialogs use the smallest width that preserves form labels and art preview. Destructive confirmation remains visually separate from ordinary Save.
- The bottom player divides identity, transport, and volume/queue into stable regions; transport remains the visual center even when metadata truncates.

## Hard rules

- Tokens only in product components. Raw visual values outside the token source are a verification failure.
- Every foreground/background text pairing must appear in the contrast table and meet WCAG AA. Focus indicators use `color.focus` and remain visible on canvas, surface, hover, and selected states.
- Shadcn registry source is mandatory before custom primitives. Domain composition cannot remove Shadcn accessibility behavior.
- Local tracks always expose Play; internet results never expose Play. `color.info` identifies internet provenance and `color.accent` identifies playable/active progress.
- One primary action per viewport/dialog. Destructive actions use the AlertDialog path and never share accent styling.
- No copied Spotify marks/assets, decorative dashboard cards, glassmorphism, neon page gradients, oversized marketing headings, floating pill clusters, or motion without state meaning.
- Truncation never hides the only source/status/error label; Tooltip supplements but does not replace accessible text.
