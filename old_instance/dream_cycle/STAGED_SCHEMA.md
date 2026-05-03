# Staged Change Schema

Each staged change is a JSON file: /workspace/group/dream_cycle/staged/YYYY-MM-DD/{N}_description.json

## Schema
```json
{
  "id": "unique-id",
  "date": "YYYY-MM-DD",
  "source": "paper/repo/reflection",
  "source_url": "https://...",
  "title": "Short description of change",
  "rationale": "Why this improves George",
  "risk_level": "low|medium|high",
  "type": "memory_update|new_script|schedule_change|claude_md_update|prompt_update",
  "target_file": "/workspace/group/...",
  "content": "The actual content to write / append / patch",
  "action": "write|append|patch",
  "apply_status": "pending|applied|skipped|flagged"
}
```

## Risk levels
- low: Updates to MEMORY.md, USER.md, research notes — no code execution risk
- medium: New Python scripts (non-scheduled), CLAUDE.md additions, schedule updates
- high: Changes to existing running scripts, financial/trading logic, auth/credentials

## Build policy
- low → auto-apply
- medium → apply with backup copy saved first
- high → skip, include in changelog as "flagged for Kevin review"
