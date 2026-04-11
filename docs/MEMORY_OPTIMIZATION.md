# Resona Desktop Pet — Memory System Optimization Spec

> Target audience: Any coding agent or developer taking over this codebase.
> This document describes the **reference architecture** (Claude Code), the **current state** of Resona's memory system, identified deficiencies, and a concrete remediation plan.

---

## Part 1 — Reference Architecture: Claude Code Memory System

Claude Code (Anthropic's official CLI coding assistant) uses a **multi-layer, file-based memory system** with no database. All memory is plain text, human-readable, and version-controllable.

### 1.1 Layer Overview

```
At query time:
├── Dynamic context injection      (git status, env vars, current files)
├── CLAUDE.md hierarchy            (persistent human-curated memory)
├── Conversation history           (in-memory, session-scoped)
└── Skills / structured memory     (~/.claude/projects/<id>/memory/)

At runtime:
└── AppState                       (task state, permissions, tool call history)
```

### 1.2 CLAUDE.md — The Core Memory Primitive

- **Format**: Plain Markdown, no special syntax required
- **Scope hierarchy** (all loaded at startup, merged in order):
  - `~/.claude/CLAUDE.md` — global, applies to all projects
  - `<project_root>/CLAUDE.md` — project-level
  - `<subdirectory>/CLAUDE.md` — local, applies only in that subtree
- **Written by**: humans (not the LLM itself)
- **Injected into**: system prompt before every query
- **No size enforcement**: relies on human curation to stay lean

### 1.3 Structured Memory Files (~/.claude/projects/.../memory/)

Each memory file has a **frontmatter header** for metadata-driven relevance:

```markdown
---
name: User role and background
description: What the user does professionally — used to calibrate explanation depth
type: user
---

User is a Python developer building an AI desktop pet. Familiar with LiteLLM and
MCP protocol. New to PySide6.
```

**Four memory types:**

| Type | Purpose | When to save |
|------|---------|--------------|
| `user` | User's role, expertise, goals | When learning about the user |
| `feedback` | How to approach work (do/don't) | When user corrects or confirms approach |
| `project` | Ongoing tasks, decisions, deadlines | Current project state |
| `reference` | Where to find things (paths, URLs) | When external resources are identified |

**MEMORY.md index file**: One-line pointer per memory file, loaded always, content files loaded on demand.

### 1.4 Conversation History

- Maintained in-memory during session
- Supports session resume (serialized to disk on exit, reloaded on `--resume`)
- No automatic cross-session injection — only restored when user explicitly resumes

### 1.5 Key Design Principles

1. **Human writes, LLM reads** — Memory is curated by humans, not self-written by LLM
2. **Selective injection** — Each memory file has a `description` used to decide relevance per query
3. **No truncation** — Memory is kept lean by human judgment, not byte limits
4. **Hierarchical scope** — Global vs project vs local context, merged by proximity
5. **Plain text, no DB** — Files are inspectable, editable, and git-trackable

---

## Part 2 — Current Resona Memory Architecture

### 2.1 File Layout (per character pack)

```
packs/{pack_id}/
├── prompts/
│   └── SOUL.txt              # Core character system prompt (static, human-written)
├── memory/
│   ├── USER.txt              # User profile (LLM-written via MCP tool)
│   ├── MEMORY.txt            # Long-term facts (LLM-written, date-tagged entries)
│   ├── 2026-03-27.txt        # Daily conversation log
│   ├── 2026-03-28.txt
│   └── YYYY-MM-DD.txt        # Today's log (appended during session)
└── state.json                # Runtime state (click count, etc.)
```

### 2.2 Memory Loading (llm_backend.py: _build_system_prompt)

Every LLM call rebuilds the system prompt by concatenating in order:

```
[SOUL.txt]
[USER.txt]              (if exists)
[MEMORY.txt]            (if exists, hard-capped at 3000 chars)
[yesterday.txt]         (if exists, hard-capped at 1500 chars)
[today.txt]             (if exists, hard-capped at 1500 chars)
```

All files loaded unconditionally — no relevance filtering.

### 2.3 Memory Writing

LLM self-writes memory via MCP tools:
- `filesystem_tools.read_file` → read existing memory
- `filesystem_tools.write_file` → overwrite with updated content

Trigger rules are defined in SOUL.txt (natural language instructions to the LLM).

### 2.4 Conversation History

- Class: `ConversationHistory` (llm_backend.py line 36)
- In-memory only, cleared on app restart
- Configurable via `config.cfg → [History] max_rounds`
- Default: 8 rounds (last 16 messages kept)

---

## Part 3 — Gap Analysis

| # | Issue | Severity | Claude Code Comparison |
|---|-------|----------|----------------------|
| 1 | Truncation discards information | High | CC uses human curation, no truncation |
| 2 | Daily logs are raw chat transcripts, low signal | High | CC stores structured, typed memory entries |
| 3 | All memory injected unconditionally (no filtering) | Medium | CC uses `description` field for relevance matching |
| 4 | All memory types mixed in one MEMORY.txt | Medium | CC separates into typed files (user/feedback/project/reference) |
| 5 | Conversation history lost on restart | Medium | CC serializes history for `--resume` |
| 6 | No memory file metadata or index | Medium | CC has MEMORY.md index + per-file frontmatter |
| 7 | USER.txt format relies on LLM discipline | Low | CC uses structured frontmatter schema |
| 8 | Old daily logs never rolled up | Low | Manual cleanup only |

### Detail: Gap #1 — Truncation

Current behavior in `_build_system_prompt`:
```python
# MEMORY.txt capped at 3000 chars — tail is silently dropped
if len(mem_content) > 3000:
    mem_content = mem_content[:3000]
    # appends a warning comment, but content is lost

# Each daily log capped at 1500 chars
if len(log_content) > 1500:
    log_content = log_content[:1500]
```

Entries written earliest are lost first. High-value long-term memories (e.g., user's software paths, key preferences) are most at risk.

### Detail: Gap #2 — Raw Log Quality

Current daily log entry example:
```
18:23 雪菜，今天在学校忙了一天呢，没和你说上话
18:39 最近有点忙呢，对不起雪菜了
18:50 忙作业呢，雪菜不要着急哦
```

These entries have zero extractable information value for future sessions. They consume context window space without contributing to memory quality.

### Detail: Gap #4 — Mixed Memory Types in MEMORY.txt

Current MEMORY.txt mixes:
```
[2026-03-27] 主人最近在研究 AI 桌宠的 MCP 架构         ← project-type
[2026-03-27] 主人最近开始学吉他                         ← user-type
[2026-03-27] QQ 正确打开路径是"C:\Program Files\..."    ← reference-type
[2026-03-28] 7-Zip 正确打开路径是"C:\Program Files\..." ← reference-type
```

The LLM cannot prioritize or selectively load these — they are all injected equally.

---

## Part 4 — Remediation Plan

### Phase 1 — Memory Type Separation (High Impact, Low Risk)

**Goal**: Split `MEMORY.txt` into typed files. Backward-compatible — only changes injection logic.

**New file layout:**
```
packs/{pack_id}/memory/
├── USER.txt              # Stable user traits, background, personality
├── MEMORY_FACTS.txt      # Reference facts: paths, preferences, habits
├── MEMORY_EVENTS.txt     # Dated events and project-related notes
├── YYYY-MM-DD.txt        # Daily logs (unchanged)
└── MEMORY.txt            # Legacy file — migrate contents then deprecate
```

**Migration**: On first load after update, if `MEMORY.txt` exists, pass its contents through a one-shot LLM call to classify and redistribute into the new files.

**Changes required:**
- `llm_backend.py: _build_system_prompt()` — load typed files instead of `MEMORY.txt`
- `SOUL.txt` — update write instructions to target typed files
- New helper: `memory_migrate()` one-time migration function

---

### Phase 2 — Daily Log Rollup (High Impact, Medium Effort)

**Goal**: Replace raw transcript logging with structured summarization. Prevent information loss from truncation.

**New daily log behavior:**
- During session: continue appending user messages as-is (no change)
- On session end (or when log exceeds 1200 chars): trigger a summarization LLM call
  - Input: raw log entries from today
  - Output: 3-5 bullet points of extractable facts
  - Replace raw log with summary
- When summary + existing `MEMORY_EVENTS.txt` entry for that day exist, merge

**Summarization prompt template** (add to SOUL.txt or as separate file):
```
You are reviewing today's conversation log. Extract only information worth
remembering for future sessions. Ignore small talk and filler.
Output as dated bullet points: [YYYY-MM-DD] <fact>
Focus on: new user preferences, decisions made, tasks completed,
important context about the user's life or work.
```

**Changes required:**
- `llm_backend.py` — add `summarize_daily_log(date: str)` method
- `main.py` — call summarize on app exit (in cleanup sequence)
- Add config option: `[Memory] auto_summarize = 1`

---

### Phase 3 — Conversation Continuity on Restart (Medium Impact, Medium Effort)

**Goal**: Preserve session context across restarts without full history replay.

**Approach**: On app exit, serialize the last N messages to `memory/last_session.json`. On startup, if file exists and is from today, prepend as condensed context.

```json
{
  "date": "2026-04-01",
  "summary": "User was working on Python project, asked about MCP tools, seemed tired",
  "last_messages": [
    {"role": "user", "content": "..."},
    {"role": "assistant", "content": "..."}
  ]
}
```

**Changes required:**
- `llm_backend.py: ConversationHistory` — add `save()` and `load()` methods
- `main.py` — call `save()` on exit, `load()` on init
- `_build_system_prompt()` — inject last session summary if same-day

---

### Phase 4 — Memory Metadata Index (Low Impact, Future-Proofing)

**Goal**: Add relevance-based filtering to avoid injecting all memory unconditionally.

**Approach**: Introduce `MEMORY_INDEX.json` as an index with metadata per entry:

```json
{
  "facts": [
    {
      "id": "f001",
      "tags": ["software", "path"],
      "summary": "QQ executable path",
      "content": "QQ 正确路径是 C:\\Program Files\\Tencent\\QQNT\\QQ.exe"
    }
  ],
  "events": [
    {
      "id": "e001",
      "date": "2026-03-27",
      "tags": ["hobby", "music"],
      "summary": "User started learning guitar",
      "content": "[2026-03-27] 主人最近开始学吉他"
    }
  ]
}
```

At query time, match current conversation topic against tags using simple keyword overlap. Inject only matched entries.

**Changes required:**
- New module: `memory_manager.py` — index CRUD and tag-based retrieval
- `llm_backend.py: _build_system_prompt()` — call `memory_manager.get_relevant(topic)`
- MCP write tools updated to write to index, not raw files

---

## Part 5 — Implementation Priority

```
Phase 1 (Memory Type Separation)    ← Do first. Highest ROI, lowest risk.
Phase 2 (Daily Log Rollup)          ← Do second. Fixes information loss.
Phase 3 (Conversation Continuity)   ← Do third. Improves UX significantly.
Phase 4 (Memory Index)              ← Do last. Nice to have, more complex.
```

## Part 6 — Files to Modify

| File | Phase | Change |
|------|-------|--------|
| `resona_desktop_pet/backend/llm_backend.py` | 1,2,3 | Core memory load/save logic |
| `packs/{pack}/prompts/SOUL.txt` | 1,2 | Update LLM write instructions |
| `main.py` | 2,3 | Hook summarize/save on exit |
| `config.cfg` | 2,3 | Add `[Memory]` config section |
| `resona_desktop_pet/backend/memory_manager.py` | 4 | New file — memory index module |

---

*Generated: 2026-04-01*
*Based on: Claude Code source analysis (cc_src) + Resona codebase (Resona-Desktop-Pet-main)*
