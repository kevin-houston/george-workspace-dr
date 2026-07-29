---
type: tool
title: Variant Switcher — prototype picker harness
description: Floating bottom-center pill for toggling named UI variants during agent-assisted prototyping, with sliding highlight, keyboard shortcuts, and URL-param persistence
tags: [workflow, prototyping, ui, agent-coding]
---

# Variant Switcher

## Origin

Pattern by @emilkowalski (July 2026 tweet + github.com/emilkowalski/skills/prototype).
Our implementation is a clean rewrite matching the spec; Emil's code was not copied.

## The workflow

1. Ask the agent for **N named variants** of a UI piece (not Option A/B/C — real directional names: Quiet, Editorial, Playful)
2. Each variant is a distinct direction you could defend shipping, not a color tweak
3. The picker harness lets you flip between them at full size; side-by-side thumbnails distort scale — always judge UI at real size
4. Share `?v=2` URL with a colleague to send them directly to variant 2
5. Pick a winner; agent integrates it and deletes the prototype surface

## Our implementation

**Files:**
- `lib/variant-switcher.js` — self-contained JS + CSS, no dependencies
- `lib/variant-switcher-demo.html` — working demo (PEAD signal card, 3 variants)

## API

```js
VariantSwitcher.init({
  stage: document.getElementById('stage'),  // where variants render
  hasMotion: true,          // show replay (↻) button; default false
  position: 'bottom',       // 'bottom' (default) | 'top'
  variants: [
    { name: 'Quiet',     render: () => `<div>...</div>` },
    { name: 'Editorial', render: () => `<div>...</div>` },
    { name: 'Playful',   render: () => `<div>...</div>` },
  ],
});
```

`render()` returns an HTML string or a DOM Node. It is called inside `requestAnimationFrame` so entrance animations re-run on every mount (including replay).

## Picker behavior

- **Bottom-center dark glass pill**, `z-index: 2147483647` — works over any page color
- **Sliding highlight**: animates between buttons at 250ms `cubic-bezier(.23,1,.32,1)`; variant swap is instant (no transition on content)
- **`data-ready`** added after first paint — prevents the highlight from animating on load
- **Reduced-motion**: highlight slide disabled via `@media (prefers-reduced-motion)`
- **`data-position="top"`** when a variant uses the bottom of the screen (toast, dock)

## Keyboard shortcuts

| Key     | Action |
|---------|--------|
| `1`–`N` | Jump to variant N |
| `←`/`→` | Step through variants |
| `R`     | Replay current (re-mounts → re-runs entrance animation) |

Keys are ignored when focus is in an input, textarea, select, or contenteditable, or when a modifier key is held.

## URL persistence

Selection written as `?v=N` (1-indexed). Shareable. Loaded on init; falls back to variant 1 if missing or out of range.

## Agent prompt pattern

> "Build 3 variants of [component]. Use the variant-switcher from `/lib/variant-switcher.js`.
> Variants:
> - **Quiet** — [description of direction]
> - **Editorial** — [description of direction]
> - **Playful** — [description of direction]
> Put them behind the picker. `hasMotion: true` if any variant has entrance animation."

## Naming conventions (from Emil's spec)

- Names describe the **direction**, not the position: "Quiet", "Editorial", "Dense", "Playful", "Structured"
- Never "Option A/B/C" — names should make the tradeoff obvious at a glance
- If two proposed variants differ only in accent color, they are one direction — replace one with a real alternative

## Craft rules (Emil's spec)

- `ease-out` on entrances, never `ease-in`
- Sub-300ms UI motion
- `transform` + `opacity` only (no layout-triggering props)
- Reduced motion handled
- No lorem ipsum; realistic content in every variant
