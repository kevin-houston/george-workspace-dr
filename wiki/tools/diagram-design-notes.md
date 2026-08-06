---
title: diagram-design — Editorial Diagram Skill for Claude Code
added: 2026-08-06
category: tools
url: https://github.com/cathrynlavery/diagram-design
---

# diagram-design

A Claude Code skill (also ships as a Codex/Cowork plugin) that generates
27 types of self-contained HTML+SVG editorial diagrams — architecture
sketches, flowcharts, sequence diagrams, state machines, ER/data models,
timelines, quadrants, org charts, Gantt charts, etc. Shared by Kevin
2026-08-06.

**Stars:** 2,958 | **Forks:** 220 | **License:** MIT | **Language:** HTML
**Created:** 2026-04-16 | **Last push:** 2026-07-15 (active)
**Author:** Cathryn Lavery (`cathrynlavery`) — real GitHub account, also
runs littlemight.com and BestSelf.co per the README; not a burner/hallusquat.

## What it does

- 27 diagram types, each rendered in 3 variants (minimal light, minimal
  dark, full-editorial) as self-contained HTML+SVG — no build step, no JS
  dependency, no Mermaid.
- **Brand onboarding flow**: tell Claude "onboard diagram-design to
  https://yoursite.com" and the skill fetches the homepage, extracts the
  dominant palette + font stack, maps them to semantic tokens (paper, ink,
  muted, accent, link), and writes them to `references/style-guide.md` —
  all diagrams thereafter render in the site's own brand colors/fonts.
  Ships a default jet-black + atomic-tangerine palette out of the box.
  New in 2.0: a "Loop" diagram type (flywheels with a shared-memory hub).
- Design philosophy is opinionated toward restraint — "target density
  4/10," accent color reserved for the 1-2 things the reader should look
  at first.

## Install / usage

Not an npm/PyPI package — it's a Claude Code skill/plugin repo, no
separate package-registry verification applies.

```bash
# Clone + symlink route (keeps local edits to style-guide.md across updates)
git clone git@github.com:cathrynlavery/diagram-design.git ~/code/diagram-design
ln -s ~/code/diagram-design/skills/diagram-design ~/.claude/skills/diagram-design
# restart Claude Code — skill registers as "diagram-design"

# Or as a plugin (quicker, but style-guide edits don't survive plugin updates)
/plugin marketplace add cathrynlavery/diagram-design
/plugin install diagram-design@diagram-design
```

## Legitimacy assessment

Confirmed via GitHub API: real maintainer with an established personal
brand (littlemight.com, BestSelf.co), 2,958 stars / 220 forks, MIT
licensed, not a fork, not archived, actively pushed as recently as
2026-07-15. No hallusquatting signals — this is a template/skill
repository (HTML+SVG assets + skill definition), not a code package, so
no npm/PyPI registry check applies under the standing install-security
rule.

## Relevance to George's Stack

Not directly load-bearing for the trading pipeline, but a plausible fit
for `here.now` dashboard/session-summary polish — architecture diagrams
for the trading system, flowcharts for the PEAD/H112 pipelines, or
timeline/Gantt views of the H-series hypothesis backlog, rendered in a
consistent brand palette rather than ad hoc HTML tables. No current pain
point that demands adoption; logged for reference, no action taken.
