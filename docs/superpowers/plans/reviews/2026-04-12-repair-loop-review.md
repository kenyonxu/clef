# Code-Driven Repair Loop -- Independent Senior Engineer Review

**Plan**: `2026-04-11-code-driven-repair-loop.md`
**Reviewer**: Independent senior engineer (no prior exposure)
**Date**: 2026-04-12

---

## 1. Architecture

**FINDING 1: Three-way config duplication for clef-repair agent** -- HIGH

`clef-repair` config appears in three places: `agents.yaml`, `_AGENT_DEFS` in `orchestrator.py`, and `_AGENT_TOOL_MAP` in `tools.py`. Any field mismatch (model, tools, turns) silently diverges. The existing agents already suffer this pattern but adding a new agent amplifies it.

**Fix**: Single source of truth. `agents.yaml` should be the canonical config loaded at runtime. `_AGENT_DEFS` and `_AGENT_TOOL_MAP` should be derived from it, not hand-maintained duplicates.

**FINDING 2: `_generate_with_best_of_n` is God-method sized** -- MEDIUM

The method handles candidate generation, deterministic fix, validation, feedback formatting, best selection, AND repair fallback. Estimated 80+ lines. This violates the <50-line function rule from coding standards and mixes orchestration policy with execution.

**Fix**: Extract `_validate_candidate(abc_text, plan_path, voice_label) -> (fail_count, failures)` and `_select_best_candidate(candidates) -> candidate`. The method becomes a 20-line coordinator.

**FINDING 3: Tight coupling between orchestrator and tool internals** -- MEDIUM

`_generate_with_best_of_n` calls `fix_measure_duration` and `validate_abc` directly via `from clef_server.tools import ...`. This means orchestrator knows tool return shapes (`result["fixes"]`, `result["abc"]`, `result["pass"]`). If the tool contract changes, orchestrator breaks silently.

**Fix**: Define typed dataclasses or Protocols for tool results (`FixResult`, `ValidationReport`) that both sides depend on.

---

## 2. Edge Cases

**FINDING 4: Tuplet duration miscounted** -- CRITICAL

`_count_measure_units` strips tuplet markers `(\d+` via regex, but does NOT divide the contained notes' durations by the tuplet count. For example, `(3c2 d2 e2` is three quarter-notes in the time of two -- total 4 units, not 6. The current code counts 6. This means every measure containing triplets will be "fixed" incorrectly, creating worse output than the LLM produced.

**Fix**: Tuplet parsing must track the multiplier. When a `(3` is encountered, subsequent notes (up to 3 of them) should have their durations multiplied by 2/3. This is genuinely hard with regex -- consider a stateful parser or deferring measures with tuplets to the repair agent (`max_deviation` won't save you because the deviation is exactly what the tuplet should have resolved).

**FINDING 5: Chord duration double-counted** -- HIGH

`_count_measure_units` strips `[` and `]` but keeps inner notes. `[CEG]4` is ONE chord with duration 4, but the regex will match C, E, G separately, each getting duration parsed from what follows. `_NOTE_RE` captures `C` with duration group looking at `EG]4` -- the regex may parse this as `C` with empty duration (1 unit) and then `E` and `G` similarly. The chord duration `4` may be picked up by one note or none. Result: chords are miscounted.

**Fix**: Before stripping brackets, extract chord durations: `\[([^\]]+?)(\d*(?:/\d+)?)\]` and count the entire chord as ONE event with the bracket duration.

**FINDING 6: `_fix_single_measure` adjusts the LAST element, but what if the last element is inside a repeat barline** -- MEDIUM

ABC supports `|: ... :|` repeat markers. If the measure text contains `:|`, the last note/rest regex match may land on the barline text rather than the actual last musical element. The regex doesn't account for repeat/barline decorations embedded in measure text.

**Fix**: Strip trailing barline markers (`:|`, `|:`, `::`) from `measure_text` before finding last note/rest.

**FINDING 7: Empty candidate with `fail_count=999` wins best-of-N if all rounds produce garbage** -- MEDIUM

If all rounds produce empty/placeholder ABC, `min(candidates, key=lambda c: c["fail_count"])` picks the one with `fail_count=999`. The caller then tries to merge this empty string, which will crash or produce corrupt output.

**Fix**: Add a guard: if `best["fail_count"] == 999`, return an error result and let the orchestrator skip that voice rather than merge garbage.

---

## 3. Tests

**FINDING 8: No test for tuplets, chords, or repeat barlines** -- HIGH

The 6 test cases in the plan cover: correct measure, short-by-1, long-by-1, multiple measures, large deviation, rest extension. Missing:
- Triplets: `(3c d e |` -- this is the most common real-world case after plain notes
- Chords: `[CEG]4 z4 |`
- Tied notes: `c2-c2 |`
- Multi-voice: V:1 and V:2 in same input
- Broken rhythm: `c>d |` (scotch snap)
- Grace notes: `{g}c2 d2 e2 f2 |`

**Fix**: Add at minimum a tuplet test (expecting skip or correct count) and a chord test. These are the two cases most likely to produce silent corruption.

**FINDING 9: No test for `_generate_with_best_of_n`** -- HIGH

The plan adds tests only for `fix_measure_duration`. The orchestrator methods (`_generate_with_best_of_n`, `_attempt_repair`, `_run_validation_from_abc`) have zero test coverage. These contain the core business logic of candidate selection and repair triggering.

**Fix**: Add `test_orchestrator.py` with mocked `_run_agent` and `validate_abc` to test: (a) round 1 passes immediately, (b) round 1 fails, round 2 passes, (c) all rounds fail, repair agent called, (d) repair makes it worse, original kept.

**FINDING 10: `_run_validation_from_abc` writes temp files but has no cleanup test** -- MEDIUM

This helper writes to `_candidate_r{N}_report.json` and temp ABC files. Under 10x load (concurrent sessions), temp file collisions or disk exhaustion are possible. No test verifies cleanup.

**Fix**: Use `tempfile.NamedTemporaryFile` or a session-scoped temp dir. Add a test that verifies temp files are cleaned up after the method returns.

---

## 4. Security

**FINDING 11: `fix_measure_duration` takes raw `abc_content` string, not a path** -- MEDIUM

Unlike other tools that use `_validate_path()` for path traversal protection, `fix_measure_duration` accepts a string. This is fine -- but the tool is marked `ToolSafety.READ_ONLY` in `_TOOL_META` despite the fact that it returns modified ABC content that the agent will then write via `write_file`. This mislabeling means any future safety audit layer that gates writes based on `ToolSafety` would incorrectly allow patterns like: agent calls `fix_measure_duration`, gets modified ABC, calls `write_file` to overwrite the score -- all within READ_ONLY + EXCLUSIVE_WRITE, which bypasses any "no read-modify-write without IDEMPOTENT_WRITE" policy.

**Fix**: Consider marking as `ToolSafety.IDEMPOTENT_WRITE` or documenting that the return value is the mutation vector.

**FINDING 12: No input length limit on `abc_content`** -- LOW

A malicious or buggy LLM could pass a multi-MB string to `fix_measure_duration`. The regex operations (`re.sub`, `finditer`) on unbounded input could cause CPU denial-of-service. The existing `read_file` has no size limit either, but `fix_measure_duration` amplifies by running multiple regexes.

**Fix**: Add `if len(abc_content) > MAX_ABC_SIZE (e.g., 100KB): return {"pass": False, "error": "Input too large"}`.

---

## 5. Hidden Complexity

**FINDING 13: `target_per_measure=0` auto-detect is fragile** -- HIGH

When `target_per_measure` is 0, the tool parses `M:` and `L:` headers. But:
- `M:C|` (cut time) is not `M:2/2` -- it needs special handling
- `M:3/8 + L:1/16` = target 6, not 3 -- the L: base unit matters
- Missing `L:` header defaults to `L:1/4` in ABC spec, but the code may assume `L:1/8`
- `M:none` (free meter) should skip all measure validation

If auto-detect returns wrong target, every measure gets "fixed" to the wrong duration.

**Fix**: Explicitly handle `M:C` and `M:C|`. Default `L:` to `1/4` per ABC spec. Return `{"pass": True, "measures_checked": 0}` for free meter.

**FINDING 14: Best-of-N multiplies cost linearly** -- MEDIUM

With `max_rounds=2` per voice and 4 voices, plus a potential repair agent call, a single composition request triggers up to 8 LLM calls + 1 repair call. At Opus pricing for composer/harmonist/rhythmist, this is 8x the current cost. The plan doesn't discuss cost budgets or rate limiting.

**Fix**: Add `total_llm_budget` parameter. Consider: only use best-of-N for voices that failed validation on round 1, not all voices unconditionally.

**FINDING 15: `_attempt_repair` is not fully specified in the plan** -- HIGH

The plan shows the signature and imports but the full body is referenced but not included in the indexed content. The review checklist says it returns `dict` with keys `abc, fail_count, failures`, but the implementation is a black box. This is the method that calls the clef-repair agent -- if it doesn't handle the case where the repair agent itself returns empty/garbage, the orchestrator will crash.

**Fix**: The implementation must include: (a) try/except around `_run_agent`, (b) empty ABC guard on repair response, (c) if repair agent fails, return original `abc_text` with original `fail_count`.

---

## Summary

| Severity | Count | Key Items |
|----------|-------|-----------|
| CRITICAL | 1 | Tuplet duration miscount (#4) |
| HIGH | 5 | Chord double-count (#5), missing orchestrator tests (#9), no tuplet/chord tests (#8), auto-detect fragility (#13), unspecified `_attempt_repair` body (#15) |
| MEDIUM | 6 | God-method (#2), coupling (#3), repeat barlines (#6), empty candidate wins (#7), temp file cleanup (#10), cost multiplier (#14) |
| LOW | 2 | Safety mislabel (#11), input length (#12) |

**Verdict**: The plan is architecturally sound but the regex-based ABC parser has two critical mathematical bugs (tuplets, chords) that will produce worse output than the LLM. The test plan covers only the happy path. Fix #4 and #5 before implementation begins -- everything else can be addressed during implementation.
