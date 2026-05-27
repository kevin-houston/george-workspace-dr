---
created: 2026-05-27
updated: 2026-05-27
source: https://github.com/WH-2099/mermaid-skill
---

# mermaid-skill — Claude Code Skill for Mermaid Diagrams

**Repo**: github.com/WH-2099/mermaid-skill  
**Author**: WH-2099  
**License**: MIT

A Claude Code skill that adds a `/mermaid` command for generating Mermaid diagrams. Supports all 23 diagram types with bundled syntax reference docs that auto-sync weekly from the official mermaid-js repo.

## Installation

```bash
# Copy skill folder into project
git clone https://github.com/WH-2099/mermaid-skill.git
cp -r mermaid-skill/.claude/skills/mermaid /path/to/project/.claude/skills/

# Or as git submodule
git submodule add https://github.com/WH-2099/mermaid-skill.git .claude/skills/mermaid-skill
ln -s mermaid-skill/.claude/skills/mermaid .claude/skills/mermaid
```

## Usage

```
/mermaid create a flowchart for user login process
/mermaid draw a sequence diagram for API authentication
/mermaid ER diagram for an e-commerce database
```

## Supported Diagram Types (23 total)

| Category | Types |
|----------|-------|
| Flow & Process | Flowchart, State Diagram, User Journey |
| Structural | Class Diagram, ER Diagram, C4 Diagram, Architecture Diagram |
| Temporal | Sequence Diagram, Gantt Chart, Timeline, Git Graph |
| Data Visualization | Pie Chart, XY Chart, Sankey Diagram, Quadrant Chart, Radar Chart, Treemap |
| Organization | Mindmap, Kanban, Block Diagram, Requirement Diagram |
| Technical | Packet Diagram, ZenUML |

## Structure

```
.claude/skills/mermaid/
├── SKILL.md           # skill definition + instructions
└── references/        # Mermaid syntax docs (one per diagram type)
```

Docs sync via GitHub Action that pulls weekly from mermaid-js/mermaid upstream.

## Relevance

Useful for documenting trading strategy flows, pipeline architecture diagrams, hypothesis dependency graphs, and system design notes within Claude Code sessions.
