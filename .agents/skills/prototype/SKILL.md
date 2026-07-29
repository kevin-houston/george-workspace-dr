---
name: prototype
description: >
  Build multiple genuinely different versions of a UI piece behind a visual
  picker so you can flip through them live and choose the winner. Only runs
  when explicitly invoked. Does not trigger on its own, does not review
  existing UI, and does not select dependencies.
---

# Prototype

A divergence skill. One job: take a described UI piece, build several genuinely
different versions of it, and render them behind a floating picker so the user
can flip through them live and promote the one that feels right.

The entire value is **divergence**. Three tints of the same idea waste the
picker — the user learns nothing by flipping between them. Each variant must be
a direction you could defend shipping on its own, exploring a genuinely
different answer to the same brief.

Divergence is not a license to drop craft. Every variant individually ships:
correct easing (`ease-out` on entrances, never `ease-in`), sub-300ms UI
motion, `transform`/`opacity` only, reduced-motion handled.

## Hard Rules

1. **Never touch production code during exploration.** Everything lives in an
   isolated prototype surface. Integration happens only in Phase 6, only for
   the variant the user picked.

2. **Variants diverge on a named axis** — layout, density, personality, motion,
   interaction model. Before building, state each variant's axis in a phrase.
   Sharing the project's design tokens is not convergence; variants *should*
   feel native to the product.

3. **Every variant fully works.** Real interactions, realistic content — actual
   product-shaped copy, plausible names and numbers. No lorem ipsum, no dead
   buttons, no "imagine this part".

4. **The picker is chrome, not a contestant.** Its appearance and behavior are
   specified in [PICKER.md](PICKER.md). Load it and follow it exactly. Its look
   is not a design decision and never adapts to the project's tokens or colors.

5. **Clean up after the choice.** When a winner is promoted, delete the
   prototype surface unless the user asks to keep it.

## Workflow

### Phase 1 — Scope

One thing per run. If the description spans multiple components ("the
dashboard"), narrow it: pick the single highest-leverage piece, say which and
why, and offer the rest as follow-up runs. Restate the brief in one sentence —
what the thing is, where it lives, what it must do.

### Phase 2 — Recon

Map the ground the variants must stand on before designing anything:

- **Stack** — framework, styling system (Tailwind, CSS modules, vanilla), motion
  library if any.
- **Tokens** — colors, radii, spacing, fonts, easing/duration variables.
  Variants use these; every variant should look like it could ship tomorrow.
- **Personality** — playful consumer app or crisp dashboard? This bounds how far
  the boldest variant may go.
- **Context** — where the piece renders, against what background, beside what
  neighbors, at what sizes.

If there is no project (empty directory or pure exploration), skip to the
standalone branch in Phase 4 and default to neutral grays, one accent, system
font stack.

### Phase 3 — Choose directions

Default **3 variants**; up to 5 when the user explicitly asks or the design
space is genuinely wide. More than 5 dilutes the comparison.

Before writing any code, list the set: a name and an axis for each. Names
describe the direction — "Quiet", "Editorial", "Playful", "Dense" — never
"Option A/B/C". If two proposed directions would differ only in accent color or
copy, they are one direction; replace one with a real alternative.

**Completion criterion:** every variant has a name and a distinct stated axis,
and no two variants share an axis position.

### Phase 4 — Build the picker harness

Two branches depending on context:

**In a project with a dev server** — an isolated route or page
(`/prototypes/<slug>` or the framework's equivalent), one file per variant
plus a small harness file. Nothing imports from the prototype surface into
production code. Reference `/lib/variant-switcher.js` from the project root for
the picker.

**No project / static context** — a single self-contained HTML file (inline
CSS and JS) the user can open directly in a browser. Embed the picker inline
following the spec in [PICKER.md](PICKER.md).

Either way:
- Render **one variant at a time, full size, in realistic surrounding context**.
  A toast needs a page behind it; a card needs siblings; a button needs a form.
  Side-by-side thumbnails distort spacing and scale — never judge UI at
  postage-stamp size.
- Switching is **instant** — the variant swap carries no transition. The picker's
  highlight slides (250ms ease-out); the content does not.
- Set `hasMotion: true` when at least one variant has an entrance animation
  worth re-triggering with the replay button.

### Phase 5 — Verify and hand off

Run the harness. Confirm every variant renders, every interaction responds, and
the console is clean. Flip through all variants yourself before presenting.

Then present the set and **stop — the choice belongs to the user**:

| # | Variant | Axis | When it wins | Its cost |
|---|---------|------|--------------|----------|
| 1 | Quiet | Minimal motion, borders over shadows | Daily-use tool | Least memorable |
| 2 | Editorial | Large type, generous whitespace | Moment deserves weight | Eats vertical space |
| 3 | Playful | Strong color, spring motion | Consumer / marketing | Out of place in dense UIs |

Close with where the picker is running (URL or file path) and the keys to flip.

**Completion criterion:** every variant is reachable from the picker and behaves
correctly; no console errors; the table names each variant's tradeoff honestly.

### Phase 6 — Promote on selection

When the user picks: integrate that variant where it belongs following the
project's conventions (file layout, naming, token usage), then delete the
prototype surface (Hard Rule 5). If the user wants another round, keep the
harness and run Phase 3 again, diverging *around* the direction they gravitated
toward.

## Invocation Variants

| Invocation | Behavior |
|------------|----------|
| `<description>` | Full workflow: scope → recon → 3 variants → picker → wait for choice |
| `<description> x5` | Same, with up to 5 variants |
| `riff <variant>` | New round: keep the harness, generate a fresh set diverging around the named variant's direction |
| `keep <variant>` | Promote that variant into the codebase and delete the prototype surface |
| `keep <variant>, leave the picker` | Promote, but keep the prototype surface around |

## Tone

Sell each variant honestly — one line on when it wins, one on what it costs.
Never pre-pick a favorite in the comparison table. If the user asks which you'd
choose, answer with a reason rooted in the product's personality and frequency
of use, not aesthetics alone. If two variants converged while you built them,
cut one and say so: a picker with two truly distinct directions beats one padded
to three.
