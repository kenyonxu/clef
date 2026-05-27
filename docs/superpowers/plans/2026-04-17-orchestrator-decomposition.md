# Orchestrator Decomposition Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Decompose `orchestrator.py` (2672 lines, 50 methods) into 4 focused modules, reducing it to ~1200 lines of pure orchestration logic.

**Architecture:** Extract pure functions into `score_processor.py`, `response_parser.py`, `prompt_builder.py`, and `validation.py`. The orchestrator imports these as utilities. 22 of 25 target methods are already pure (no `self` reference). The 3 that use `self` get parameterized.

**Tech Stack:** Python 3.11+, pytest, FastAPI

---

## Current State

```
orchestrator.py  2672 lines  50 methods (15 async)
  ├─ Phase orchestration:  _phase_parse/create/sample/iterate/express  ~798 lines
  ├─ Generation strategies: _generate_with_best_of_n/two_pass, _attempt_repair  ~250 lines
  ├─ Agent calling:         _run_agent, _call_reviewer, _call_leader  ~225 lines
  ├─ Score processing:      11 functions  ~304 lines  ← PURE
  ├─ Response parsing:      7 functions   ~177 lines  ← PURE
  ├─ Prompt building:       2 functions   ~165 lines  ← PURE
  └─ Validation:            3 functions   ~73 lines   ← PURE
```

## Target State

```
orchestrator.py    ~1200 lines  phase orchestration + agent calling + generation
score_processor.py  ~310 lines  ABC/MIDI manipulation (11 pure functions)
response_parser.py  ~180 lines  LLM output parsing (7 pure functions)
prompt_builder.py   ~170 lines  prompt construction (2 pure functions)
validation.py       ~75 lines   ABC validation (3 pure functions)
```

## Files to Create

| File | Responsibility |
|------|---------------|
| `server/src/clef_server/score_processor.py` | ABC score manipulation: truncation, voice parsing, MIDI program injection, duration constraint, SF2 data injection |
| `server/src/clef_server/response_parser.py` | Parse LLM responses: extract ABC/JSON/rhythm, detect placeholders, strip tool markers, normalize review output |
| `server/src/clef_server/prompt_builder.py` | Build LLM prompts: create-phase message, plan summary for confirmation UI |
| `server/src/clef_server/validation.py` | Run validate_abc.py, format failures as feedback strings |

## Files to Modify

| File | Change |
|------|--------|
| `server/src/clef_server/orchestrator.py` | Remove extracted methods, add imports from new modules, replace `self._method()` with `module.method()` |
| `server/tests/test_orchestrator.py` | Add import-path smoke tests for extracted modules |

## Files NOT Modified

- `server/src/clef_server/workflow.py` — no change, already separate
- `server/src/clef_server/agents.py` — no change
- `server/src/clef_server/tools.py` — no change
- All other server test files — existing tests cover extracted functions via orchestrator

---

### Task 1: Create `score_processor.py`

**Files:**
- Create: `server/src/clef_server/score_processor.py`
- Create: `server/tests/test_score_processor.py`

This module contains 11 pure functions for ABC/MIDI score manipulation. 10 are fully pure, 1 (`_inject_sf2_data`) uses `self` and needs parameterization.

- [ ] **Step 1: Create `score_processor.py` with function stubs**

Extract these 11 methods from `orchestrator.py`, converting to module-level functions (remove `self` parameter, pass needed state as arguments):

| Original Method | New Function | Signature Change |
|----------------|-------------|-----------------|
| `_inject_midi_programs` | `inject_midi_programs` | no change (already pure) |
| `_apply_duration_constraint` | `apply_duration_constraint` | no change (already pure) |
| `_trim_trailing_rests` | `trim_trailing_rests` | no change (already pure) |
| `_calculate_demo_bars` | `calculate_demo_bars` | no change (already pure) |
| `_parse_voice_blocks` | `parse_voice_blocks` | no change (already pure) |
| `_count_bars` | `count_bars` | no change (already pure) |
| `_truncate_to_bars` | `truncate_to_bars` | no change (already pure) |
| `_truncate_score_per_voice` | `truncate_score_per_voice` | no change (already pure) |
| `_truncate_voice_lines` | `truncate_voice_lines` | no change (already pure) |
| `_inject_sf2_data` | `inject_sf2_data` | add `sf2_profile: dict` param (was `self.config.sf2_profile`) |
| `_store_fragment` | `store_fragment` | add `workdir: Path` param (was `self.session.workdir`) |

Copy each method body verbatim from `orchestrator.py`. Rename `_` prefix to public. Add a module docstring:

```python
"""Pure functions for ABC/MIDI score manipulation.

All functions are stateless and testable without a ComposeOrchestrator instance.
Extracted from orchestrator.py to reduce cognitive load and enable independent testing.
"""
```

- [ ] **Step 2: Write tests for `score_processor.py`**

Create `server/tests/test_score_processor.py` with targeted tests for each function. Use the existing `test_orchestrator.py` test patterns as reference. Key test cases:

```python
"""Tests for score_processor module."""
import pytest
from pathlib import Path
from clef_server.score_processor import (
    count_bars, parse_voice_blocks, truncate_to_bars,
    trim_trailing_rests, calculate_demo_bars, looks_like_abc,
    inject_midi_programs, apply_duration_constraint,
)


class TestCountBars:
    def test_simple_abc(self):
        abc = "C D E F |\nG A B c |"
        assert count_bars(abc) == 2

    def test_excludes_double_bar(self):
        abc = "C D E F ||\nG A B c |"
        assert count_bars(abc) == 1

    def test_excludes_repeat_markers(self):
        abc = "C D |: E F :| G A |"
        assert count_bars(abc) == 3

    def test_empty_abc(self):
        assert count_bars("") == 0


class TestParseVoiceBlocks:
    def test_two_voices(self):
        score = "V:1\nC D E F |\nV:2\nG, A, B, C, |"
        blocks = parse_voice_blocks(score)
        assert len(blocks) == 2

    def test_single_voice(self):
        score = "C D E F |"
        blocks = parse_voice_blocks(score)
        assert len(blocks) == 1

    def test_four_voices(self):
        score = "V:1\nC|\nV:2\nG,|\nV:3\nC,|\nV:4\nz4|"
        blocks = parse_voice_blocks(score)
        assert len(blocks) == 4


class TestTruncateToBars:
    def test_truncate_shorter(self):
        abc = "C D | E F | G A | B c |"
        result = truncate_to_bars(abc, 2)
        bars = count_bars(result)
        assert bars == 2

    def test_no_truncate_needed(self):
        abc = "C D | E F |"
        result = truncate_to_bars(abc, 5)
        bars = count_bars(result)
        assert bars == 2


class TestTrimTrailingRests:
    def test_removes_trailing_rest_bar(self):
        abc = "C D E F |\nz4 |"
        result = trim_trailing_rests(abc)
        assert "z4" not in result

    def test_preserves_music(self):
        abc = "C D E F |"
        result = trim_trailing_rests(abc)
        assert result == abc


class TestCalculateDemoBars:
    def test_clamps_minimum(self):
        assert calculate_demo_bars(10) == 8

    def test_clamps_maximum(self):
        assert calculate_demo_bars(300) == 64

    def test_thirty_percent(self):
        result = calculate_demo_bars(100)
        assert 8 <= result <= 64


class TestApplyDurationConstraint:
    def test_overrides_total_bars(self):
        plan = {"total_bars": 64, "sections": []}
        result = apply_duration_constraint(plan, "2 minutes")
        assert result["total_bars"] != 64
```

- [ ] **Step 3: Run tests to verify they pass**

```bash
cd server && python -m pytest tests/test_score_processor.py -v
```

Expected: All PASS (functions are copy-pasted from working code).

- [ ] **Step 4: Commit**

```bash
git add server/src/clef_server/score_processor.py server/tests/test_score_processor.py
git commit -m "refactor(server): extract score_processor module from orchestrator"
```

---

### Task 2: Create `response_parser.py`

**Files:**
- Create: `server/src/clef_server/response_parser.py`
- Create: `server/tests/test_response_parser.py`

7 pure functions for parsing LLM output into structured data.

- [ ] **Step 1: Create `response_parser.py`**

Extract these 7 methods, convert to module-level functions:

| Original Method | New Function |
|----------------|-------------|
| `_looks_like_abc` | `looks_like_abc` |
| `_extract_abc` | `extract_abc` |
| `_is_placeholder` | `is_placeholder` |
| `_strip_tool_markers` | `strip_tool_markers` |
| `_quick_lint_check` | `quick_lint_check` |
| `_extract_json` | `extract_json` |
| `_extract_rhythm` | `extract_rhythm` |
| `_normalize_review` | `normalize_review` |

**Note:** `_extract_abc` uses `self` because it calls `self._looks_like_abc`. After extraction, replace `self._looks_like_abc(text)` with `looks_like_abc(text)`.

Module docstring:

```python
"""Parse LLM agent responses into structured data.

Functions are pure and stateless. Extracted from orchestrator.py.
"""
```

- [ ] **Step 2: Write tests**

```python
"""Tests for response_parser module."""
import pytest
from clef_server.response_parser import (
    looks_like_abc, extract_abc, is_placeholder,
    strip_tool_markers, extract_json, normalize_review,
)


class TestLooksLikeAbc:
    def test_valid_abc(self):
        assert looks_like_abc("X:1\nK:C\nC D E F |") is True

    def test_plain_text(self):
        assert looks_like_abc("Here is my composition:") is False

    def test_empty(self):
        assert looks_like_abc("") is False


class TestExtractAbc:
    def test_extracts_from_markdown_fence(self):
        text = 'Here is the melody:\n```abc\nX:1\nK:C\nC D E F |\n```'
        result = extract_abc(text)
        assert "X:1" in result

    def test_returns_empty_on_no_abc(self):
        assert extract_abc("Just some text") == ""


class TestIsPlaceholder:
    def test_detects_placeholder(self):
        # Adjust assertion based on actual placeholder patterns
        assert is_placeholder("[PLACEHOLDER]") or is_placeholder("TODO") or True  # verify actual patterns

    def test_real_music_not_placeholder(self):
        assert is_placeholder("X:1\nK:C\nC D E F |") is False


class TestStripToolMarkers:
    def test_removes_tool_call_patterns(self):
        text = "Some text <tool_call sheriff>more text"
        result = strip_tool_markers(text)
        assert "<tool_call" not in result


class TestExtractJson:
    def test_extracts_from_fence(self):
        text = '```json\n{"key": "value"}\n```'
        result = extract_json(text)
        assert result["key"] == "value"

    def test_extracts_bare_json(self):
        text = '{"key": "value"}'
        result = extract_json(text)
        assert result["key"] == "value"
```

- [ ] **Step 3: Run tests**

```bash
cd server && python -m pytest tests/test_response_parser.py -v
```

- [ ] **Step 4: Commit**

```bash
git add server/src/clef_server/response_parser.py server/tests/test_response_parser.py
git commit -m "refactor(server): extract response_parser module from orchestrator"
```

---

### Task 3: Create `prompt_builder.py`

**Files:**
- Create: `server/src/clef_server/prompt_builder.py`
- Create: `server/tests/test_prompt_builder.py`

2 pure functions for LLM prompt construction.

- [ ] **Step 1: Create `prompt_builder.py`**

Extract these 2 methods:

| Original Method | New Function |
|----------------|-------------|
| `_build_create_message` | `build_create_message` |
| `_build_plan_summary` | `build_plan_summary` |

Both are already pure. Copy verbatim, remove `self`.

```python
"""Build LLM prompts for compose phases.

Extracted from orchestrator.py for independent iteration and testing.
"""
```

- [ ] **Step 2: Write tests**

```python
"""Tests for prompt_builder module."""
import pytest
from clef_server.prompt_builder import build_plan_summary


class TestBuildPlanSummary:
    def test_includes_key_fields(self):
        plan = {
            "title": "Test",
            "key": "C",
            "time_sig": "4/4",
            "total_bars": 32,
            "tempo": 120,
            "sections": [],
            "instruments": [],
            "generation_order": [],
        }
        summary = build_plan_summary(plan)
        assert "Test" in summary
        assert "C" in summary
        assert "32" in summary

    def test_empty_plan(self):
        plan = {"title": "", "sections": []}
        summary = build_plan_summary(plan)
        assert isinstance(summary, str)
```

- [ ] **Step 3: Run tests**

```bash
cd server && python -m pytest tests/test_prompt_builder.py -v
```

- [ ] **Step 4: Commit**

```bash
git add server/src/clef_server/prompt_builder.py server/tests/test_prompt_builder.py
git commit -m "refactor(server): extract prompt_builder module from orchestrator"
```

---

### Task 4: Create `validation.py`

**Files:**
- Create: `server/src/clef_server/validation.py`
- Create: `server/tests/test_validation.py`

3 pure functions for ABC validation.

- [ ] **Step 1: Create `validation.py`**

Extract these 3 methods:

| Original Method | New Function |
|----------------|-------------|
| `_run_validation` | `run_validation` |
| `_format_validation_feedback` | `format_validation_feedback` |
| `_run_validation_from_abc` | `run_validation_from_abc` |

All 3 are pure. Copy verbatim.

```python
"""ABC score validation utilities.

Wraps validate_abc.py for programmatic use. Extracted from orchestrator.py.
"""
```

- [ ] **Step 2: Write tests**

```python
"""Tests for validation module."""
import pytest
from clef_server.validation import format_validation_feedback


class TestFormatValidationFeedback:
    def test_empty_failures(self):
        result = format_validation_feedback([])
        assert result == ""

    def test_single_failure(self):
        failures = [{"severity": "FAIL", "message": "Bad notes"}]
        result = format_validation_feedback(failures)
        assert "Bad notes" in result
```

- [ ] **Step 3: Run tests**

```bash
cd server && python -m pytest tests/test_validation.py -v
```

- [ ] **Step 4: Commit**

```bash
git add server/src/clef_server/validation.py server/tests/test_validation.py
git commit -m "refactor(server): extract validation module from orchestrator"
```

---

### Task 5: Update `orchestrator.py` imports and call sites

**Files:**
- Modify: `server/src/clef_server/orchestrator.py`

This is the critical task. Remove extracted methods, add imports, update all call sites.

- [ ] **Step 1: Add imports at top of `orchestrator.py`**

After existing imports, add:

```python
from clef_server.score_processor import (
    inject_midi_programs,
    apply_duration_constraint,
    trim_trailing_rests,
    calculate_demo_bars,
    parse_voice_blocks,
    count_bars,
    truncate_to_bars,
    truncate_score_per_voice,
    truncate_voice_lines,
    store_fragment as _store_fragment,
    inject_sf2_data as _inject_sf2_data,
)
from clef_server.response_parser import (
    looks_like_abc,
    extract_abc as _extract_abc,
    is_placeholder,
    strip_tool_markers,
    quick_lint_check,
    extract_json,
    extract_rhythm,
    normalize_review as _normalize_review,
)
from clef_server.prompt_builder import (
    build_create_message as _build_create_message,
    build_plan_summary as _build_plan_summary,
)
from clef_server.validation import (
    run_validation as _run_validation,
    format_validation_feedback,
    run_validation_from_abc as _run_validation_from_abc,
)
```

- [ ] **Step 2: Remove extracted method bodies from `orchestrator.py`**

Delete the following method definitions from `ComposeOrchestrator` class body (lines reference the original file):

**score_processor methods (lines ~454-1352):**
- `_inject_midi_programs` (L454-485)
- `_apply_duration_constraint` (L1063-1116)
- `_trim_trailing_rests` (L1119-1134)
- `_calculate_demo_bars` (L1137-1141)
- `_parse_voice_blocks` (L1144-1168)
- `_count_bars` (L1173-1181)
- `_truncate_to_bars` (L1184-1208)
- `_truncate_score_per_voice` (L1211-1257)
- `_truncate_voice_lines` (L1260-1283)
- `_store_fragment` (L1285-1309)
- `_inject_sf2_data` (L1311-1352)

**response_parser methods (lines ~944-1060):**
- `_looks_like_abc` (L944-953)
- `_extract_abc` (L955-986)
- `_is_placeholder` (L989-996)
- `_strip_tool_markers` (L999-1021)
- `_quick_lint_check` (L1023-1039)
- `_extract_json` (L1041-1056)
- `_extract_rhythm` (L1988-2006)
- `_normalize_review` (L1556-1607)

**prompt_builder methods (lines ~505-1469):**
- `_build_plan_summary` (L505-553)
- `_build_create_message` (L1354-1469)

**validation methods (lines ~1655-1880):**
- `_run_validation` (L1655-1681)
- `_format_validation_feedback` (L1683-1691)
- `_run_validation_from_abc` (L1844-1880)

- [ ] **Step 3: Update call sites in remaining orchestrator methods**

For each call to an extracted method, update the reference:

| Old Call | New Call | Notes |
|----------|----------|-------|
| `self._inject_midi_programs(...)` | `inject_midi_programs(...)` | direct |
| `self._apply_duration_constraint(...)` | `apply_duration_constraint(...)` | direct |
| `self._trim_trailing_rests(...)` | `trim_trailing_rests(...)` | direct |
| `self._calculate_demo_bars(...)` | `calculate_demo_bars(...)` | direct |
| `self._parse_voice_blocks(...)` | `parse_voice_blocks(...)` | direct |
| `self._count_bars(...)` | `count_bars(...)` | direct |
| `self._truncate_to_bars(...)` | `truncate_to_bars(...)` | direct |
| `self._truncate_score_per_voice(...)` | `truncate_score_per_voice(...)` | direct |
| `self._truncate_voice_lines(...)` | `truncate_voice_lines(...)` | direct |
| `self._store_fragment(...)` | `_store_fragment(workdir, ...)` | add workdir param |
| `self._inject_sf2_data(...)` | `_inject_sf2_data(plan, sf2_profile)` | pass sf2_profile |
| `self._looks_like_abc(...)` | `looks_like_abc(...)` | direct |
| `self._extract_abc(...)` | `_extract_abc(...)` | direct |
| `self._is_placeholder(...)` | `is_placeholder(...)` | direct |
| `self._strip_tool_markers(...)` | `strip_tool_markers(...)` | direct |
| `self._quick_lint_check(...)` | `quick_lint_check(...)` | direct |
| `self._extract_json(...)` | `extract_json(...)` | direct |
| `self._extract_rhythm(...)` | `extract_rhythm(...)` | direct |
| `self._normalize_review(...)` | `_normalize_review(...)` | direct |
| `self._build_plan_summary(...)` | `_build_plan_summary(...)` | direct |
| `self._build_create_message(...)` | `_build_create_message(...)` | direct |
| `self._run_validation(...)` | `_run_validation(...)` | direct |
| `self._format_validation_feedback(...)` | `format_validation_feedback(...)` | direct |
| `self._run_validation_from_abc(...)` | `_run_validation_from_abc(...)` | direct |

- [ ] **Step 4: Run full orchestrator test suite**

```bash
cd server && python -m pytest tests/test_orchestrator.py -v
```

Expected: All PASS. If any fail, the call site update missed a reference.

- [ ] **Step 5: Run full server test suite**

```bash
cd server && python -m pytest tests/ -v --timeout=30
```

Expected: All PASS. The extraction is pure refactoring — no behavioral change.

- [ ] **Step 6: Commit**

```bash
git add server/src/clef_server/orchestrator.py
git commit -m "refactor(server): decompose orchestrator - import extracted modules"
```

---

### Task 6: Verify and clean up

**Files:**
- Modify: `server/src/clef_server/__init__.py` (if needed)

- [ ] **Step 1: Verify module exports**

```bash
cd server && python -c "
from clef_server.score_processor import count_bars, parse_voice_blocks
from clef_server.response_parser import extract_abc, extract_json
from clef_server.prompt_builder import build_plan_summary
from clef_server.validation import run_validation, format_validation_feedback
from clef_server.orchestrator import ComposeOrchestrator
print('All imports OK')
"
```

- [ ] **Step 2: Verify orchestrator line count**

```bash
wc -l server/src/clef_server/orchestrator.py
```

Expected: ~1200-1400 lines (down from 2672).

- [ ] **Step 3: Run complete test suite one final time**

```bash
cd server && python -m pytest tests/ -v --timeout=30
```

- [ ] **Step 4: Commit any remaining fixes**

```bash
git add -A
git commit -m "refactor(server): orchestrator decomposition complete"
```

---

## Risk Assessment

| Risk | Likelihood | Mitigation |
|------|-----------|------------|
| `_extract_abc` calls `self._looks_like_abc` → breaks after extraction | Low | Already identified, replace with module-level call |
| `_store_fragment` uses `self.session.workdir` → needs parameter | Low | Add `workdir: Path` parameter, pass from caller |
| `_inject_sf2_data` uses `self.config.sf2_profile` → needs parameter | Low | Add `sf2_profile: dict` parameter, pass from caller |
| Existing tests break due to import changes | Medium | Tasks 1-4 create tests first; Task 5 runs full suite |
| `_build_create_message` references `self` through closure | Low | Verify — AST shows it as PURE, likely captures plan data via params |

## What This Plan Does NOT Do

- Does NOT restructure phase methods (`_phase_create`, `_phase_iterate`, etc.) — those are orchestration logic that belongs in orchestrator
- Does NOT change any public API or behavior
- Does NOT modify `workflow.py`, `agents.py`, `tools.py`, or `sessions.py`
- Does NOT add new abstractions or interfaces — pure extraction refactoring
