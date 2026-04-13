"""
PoC: Two-Pass Generation vs Single-Pass for ABC Notation

Hypothesis: If we separate rhythm (durations) from pitch, the LLM
will produce valid measure durations more reliably because:
1. Rhythm-only has fewer tokens to manage
2. Duration counting is isolated from pitch decisions
3. Validation is trivial (just sum integers)

Experiment:
  Pass 1: Generate rhythm skeleton (durations only, no pitches)
  Pass 2: Fill pitches into validated rhythm skeleton
  Compare: Single-pass full ABC generation

Usage:
  # Dry run (no API calls, tests the parsing logic)
  python server/tests/poc_two_pass_generation.py --dry-run

  # Live test against GLM
  python server/tests/poc_two_pass_generation.py --live
"""

import re
import json
import asyncio
import argparse
from pathlib import Path

# ---------------------------------------------------------------------------
# Rhythm skeleton format: just duration values per measure
# ---------------------------------------------------------------------------
# Example: "2 2 2 2 | 2 2 1 1 2 |" means:
#   Measure 1: four quarter notes (2+2+2+2=8 units in L:1/8)
#   Measure 2: two quarters + two eighths + one quarter (2+2+1+1+2=8)
#
# This is MUCH easier for LLMs to get right because:
# - Each number represents ONE note's duration
# - Sum must equal target (8 for 4/4 time)
# - No pitch/octave/accidental complexity

TARGET_UNITS = 8  # M:4/4 + L:1/8


def validate_rhythm_skeleton(skeleton: str, target: int = TARGET_UNITS) -> dict:
    """Validate a rhythm skeleton. Much simpler than full ABC validation.

    Returns {"pass": bool, "measures": [...], "fail_count": int}
    """
    measures = skeleton.strip().split("|")
    results = []
    fail_count = 0

    for i, meas in enumerate(measures):
        meas = meas.strip()
        if not meas:
            continue

        # Parse duration values (handle rests like z, z2, z4)
        try:
            durations = []
            for token in meas.split():
                token = token.strip()
                if not token:
                    continue
                if token.startswith("z"):
                    # Rest: z=1, z2=2, z4=4
                    rest_val = token[1:]
                    durations.append(float(rest_val) if rest_val else 1.0)
                else:
                    durations.append(float(token))
        except ValueError:
            results.append({"measure": i + 1, "tokens": meas, "sum": "PARSE_ERROR", "ok": False})
            fail_count += 1
            continue

        total = sum(durations)
        ok = abs(total - target) < 0.01

        if not ok:
            fail_count += 1

        results.append({
            "measure": i + 1,
            "durations": durations,
            "sum": total,
            "target": target,
            "ok": ok,
        })

    return {"passed": fail_count == 0, "measures": results, "fail_count": fail_count}


def fill_pitches(rhythm_skeleton: str, scale: list[str] = None) -> str:
    """Fill pitches into a validated rhythm skeleton.

    This is a SIMPLE demonstration — real implementation would use the LLM.
    Here we just assign scale degrees to demonstrate the concept.
    """
    if scale is None:
        # C major scale in comfortable register
        scale = ["c", "d", "e", "f", "g", "a", "b"]

    measures = rhythm_skeleton.strip().split("|")
    filled_measures = []
    scale_idx = 0

    for meas in measures:
        meas = meas.strip()
        if not meas:
            continue

        durations = meas.split()
        notes = []
        for d in durations:
            d_val = float(d)
            pitch = scale[scale_idx % len(scale)]
            scale_idx += 1

            # Convert duration to ABC suffix
            if d_val == 1:
                notes.append(pitch)
            elif d_val == 0.5:
                notes.append(f"{pitch}/2")
            elif d_val == int(d_val):
                notes.append(f"{pitch}{int(d_val)}")
            else:
                # Fractional like 1.5 → "3/2"
                num = int(d_val * 2)
                notes.append(f"{pitch}{num}/2")

        filled_measures.append(" ".join(notes))

    return " | ".join(filled_measures) + " |"


def rhythm_skeleton_to_prompt_instruction(bars: int = 8) -> str:
    """Generate the prompt for rhythm-only generation."""
    return f"""Generate a {bars}-measure rhythm skeleton for a melody in 4/4 time.

RULES:
- Output ONLY duration values separated by spaces, measures separated by |
- Each duration represents one note/rest in L:1/8 units
- L:1/8 + M:4/4 means each measure MUST sum to exactly 8
- Use these duration values:
  1 = eighth note, 2 = quarter note, 3 = dotted quarter, 4 = half note, 6 = dotted half, 8 = whole note
  0.5 = sixteenth note (use sparingly)
  Rests: prefix with 'z' (e.g., z2 = quarter rest = 2 units)

DURATION TABLE:
  Value | Note type   | Units
  1     | eighth      | 1
  2     | quarter     | 2
  3     | dotted qtr  | 3
  4     | half        | 4
  6     | dotted half | 6
  8     | whole       | 8
  0.5   | sixteenth   | 0.5

EXAMPLE (4 measures):
2 2 2 2 | 4 4 | 2 2 1 1 2 | 3 1 2 2 |

Output exactly {bars} measures. Sum each measure to verify = 8."""


def single_pass_prompt(bars: int = 8) -> str:
    """Generate the prompt for single-pass full ABC generation."""
    return f"""Generate a {bars}-measure melody in ABC notation.

Key: C major. Time: 4/4. L:1/8.
Output only V:1 ABC notes (no headers).

RULES:
- Each measure MUST sum to exactly 8 duration units (L:1/8 base)
- Duration suffixes: (none)=1, 2=quarter, 4=half, 3=dotted quarter
- Use notes c d e f g a b (C4-B4 register)
- Create a memorable melodic phrase with clear phrasing

Duration table:
  c = eighth (1 unit), c2 = quarter (2 units), c4 = half (4 units)
  c3 = dotted quarter (3 units), c/2 = sixteenth (0.5 units)
  z = eighth rest (1 unit), z2 = quarter rest (2 units)

Output exactly {bars} measures. Verify each measure sums to 8."""


# ---------------------------------------------------------------------------
# Simplified full ABC duration validator (standalone, no tools.py dependency)
# ---------------------------------------------------------------------------
_NOTE_DUR_RE = re.compile(r"([a-gA-Gz][',]*)(\d*(?:/\d+)?)")

def _parse_dur(s: str) -> float:
    if not s:
        return 1.0
    if "/" in s:
        parts = s.split("/")
        return (float(parts[0]) if parts[0] else 1.0) / (float(parts[1]) if parts[1] else 2.0)
    return float(s)

def validate_full_abc(abc: str) -> dict:
    """Simplified measure duration validator for PoC purposes."""
    lines = abc.strip().split("\n")
    results = []
    fail_count = 0
    meas_idx = 0
    for line in lines:
        stripped = line.strip()
        if not stripped or stripped.startswith(("X:", "T:", "M:", "L:", "K:", "V:", "W:", "%")):
            continue
        if stripped.startswith("V:") and len(stripped) < 10:
            continue
        parts = stripped.split("|")
        for part in parts:
            p = part.strip()
            if not p:
                continue
            meas_idx += 1
            total = 0.0
            text = re.sub(r"%.*$", "", p)
            text = re.sub(r"![^!]*!", "", text)
            text = text.replace("[", " ").replace("]", " ")
            text = re.sub(r"\(\d+", " ", text)
            for m in _NOTE_DUR_RE.finditer(text):
                total += _parse_dur(m.group(2))
            ok = abs(total - TARGET_UNITS) < 0.01
            if not ok:
                fail_count += 1
            results.append({"measure": meas_idx, "text": p, "sum": total, "target": TARGET_UNITS, "ok": ok})
    return {"passed": fail_count == 0, "measures": results, "fail_count": fail_count}


# ---------------------------------------------------------------------------
# Dry run tests
# ---------------------------------------------------------------------------

def dry_run():
    """Test the parsing and validation logic without API calls."""
    print("=" * 60)
    print("PoC: Two-Pass Generation — Dry Run Tests")
    print("=" * 60)

    # Test 1: Valid rhythm skeleton
    print("\n--- Test 1: Valid rhythm skeleton ---")
    skeleton = "2 2 2 2 | 4 4 | 2 2 1 1 2 | 3 1 2 2 | 6 2 | 4 2 2 | 2 2 4 | 8 |"
    result = validate_rhythm_skeleton(skeleton)
    print(f"Skeleton: {skeleton}")
    print(f"Passed: {result['passed']}, Failures: {result['fail_count']}")
    for m in result['measures']:
        status = "OK" if m['ok'] else "X"
        print(f"  M{m['measure']}: {m['durations']} = {m['sum']} {status}")

    # Test 2: Invalid skeleton (what LLMs typically produce)
    print("\n--- Test 2: Invalid rhythm skeleton (typical LLM error) ---")
    bad_skeleton = "2 2 2 2 | 4 2 2 | 2 2 1 1 | 3 1 2 | 2 2 2 | 4 2 2 1 | 2 2 4 | 2 2 2 2 2 |"
    result = validate_rhythm_skeleton(bad_skeleton)
    print(f"Skeleton: {bad_skeleton}")
    print(f"Passed: {result['passed']}, Failures: {result['fail_count']}")
    for m in result['measures']:
        if not m['ok']:
            status = f"X OFF by {m['sum'] - m['target']}"
        else:
            status = "OK"
        print(f"  M{m['measure']}: {m['durations']} = {m['sum']} {status}")

    # Test 3: Fill pitches into valid skeleton
    print("\n--- Test 3: Pitch filling on validated skeleton ---")
    skeleton = "2 2 2 2 | 4 4 | 2 2 1 1 2 | 3 1 2 2 |"
    abc = fill_pitches(skeleton)
    print(f"Skeleton: {skeleton}")
    print(f"ABC:      {abc}")

    # Test 4: Prompt comparison
    print("\n--- Test 4: Prompt comparison ---")
    rhythm_prompt = rhythm_skeleton_to_prompt_instruction(8)
    full_prompt = single_pass_prompt(8)
    print(f"Rhythm prompt length: {len(rhythm_prompt)} chars")
    print(f"Full ABC prompt length: {len(full_prompt)} chars")
    print(f"Ratio: {len(rhythm_prompt) / len(full_prompt):.1f}x")
    print("\nRhythm prompt (first 200 chars):")
    print(rhythm_prompt[:200] + "...")
    print("\nFull ABC prompt (first 200 chars):")
    print(full_prompt[:200] + "...")

    # Test 5: Error surface comparison
    print("\n--- Test 5: Error surface comparison ---")
    print("Single-pass (full ABC) can fail on:")
    print("  - measure_duration (counting units)")
    print("  - pitch spelling (wrong octave, wrong accidental)")
    print("  - chord syntax ([CEG] brackets)")
    print("  - tie syntax (a-b across barlines)")
    print("  - decoration marks (!mf!, !f!)")
    print("  - voice alignment (V:1 vs V:2)")
    print("  Total error categories: ~6")
    print()
    print("Two-pass (rhythm first) can fail on:")
    print("  - measure_duration (counting units) — SAME")
    print("  - invalid duration values (e.g., '7' or 'abc')")
    print("  Total error categories: ~2")
    print()
    print("Conclusion: Two-pass reduces error surface by ~3x")

    print("\n" + "=" * 60)
    print("Dry run complete. Use --live to test against LLM.")
    print("=" * 60)


# ---------------------------------------------------------------------------
# Live test against LLM
# ---------------------------------------------------------------------------

async def live_test():
    """Test both approaches against the actual LLM."""
    print("=" * 60)
    print("PoC: Two-Pass Generation — Live Test")
    print("=" * 60)

    # Load config
    server_root = Path(__file__).parent.parent
    config_dir = server_root / "config"
    import sys
    sys.path.insert(0, str(server_root / "src"))

    from clef_server.config import load_provider_config
    from clef_server.providers import create_providers

    provider_config = load_provider_config(config_dir / "providers.yaml")
    providers = create_providers(provider_config)

    if not providers:
        print("No providers configured. Check config/providers.yaml.")
        return

    # Pick the first available provider
    provider_name = list(providers.keys())[0]
    client = providers[provider_name]
    print(f"Using provider: {provider_name}")

    from clef_server.agent_loop import run_agent_loop

    # Test 1: Rhythm-only generation
    print("\n--- Test A: Rhythm-only generation ---")
    rhythm_prompt = rhythm_skeleton_to_prompt_instruction(8)
    result_a = await run_agent_loop(
        client=client,
        system_prompt="You are a rhythm generator. Output ONLY numbers and | characters. No explanation.",
        user_message=rhythm_prompt,
        temperature=0.7,
        max_tool_calls=1,
        max_tokens=500,
    )
    rhythm_output = result_a.text.strip()
    print(f"LLM output: {rhythm_output}")
    validation_a = validate_rhythm_skeleton(rhythm_output)
    print(f"Passed: {validation_a['passed']}, Failures: {validation_a['fail_count']}")

    # Test 2: Full ABC generation
    print("\n--- Test B: Single-pass full ABC generation ---")
    full_prompt = single_pass_prompt(8)
    result_b = await run_agent_loop(
        client=client,
        system_prompt="You are a melody composer. Output only ABC notation.",
        user_message=full_prompt,
        temperature=0.7,
        max_tool_calls=1,
        max_tokens=500,
    )
    abc_output = result_b.text.strip()
    print(f"LLM output: {abc_output[:200]}...")

    # Validate the full ABC using simplified duration counting
    full_abc = f"X:1\nM:4/4\nL:1/8\nK:C\nV:1\n{abc_output}"
    b_result = validate_full_abc(full_abc)
    print(f"Passed: {b_result['passed']}, Failures: {b_result['fail_count']}")
    for m in b_result['measures']:
        if not m['ok']:
            print(f"  M{m['measure']}: {m['text'][:50]}... = {m['sum']} (off by {m['sum'] - TARGET_UNITS})")

    # Test 3: Two-pass (rhythm + pitch fill)
    print("\n--- Test C: Two-pass (rhythm → pitch fill) ---")
    if validation_a['passed']:
        # Use the validated rhythm from Test A
        fill_prompt = f"""Fill pitches into this validated rhythm skeleton.
Each number represents a duration in L:1/8 units.
Replace each number with a note from C major scale (c,d,e,f,g,a,b).

Rules:
- Keep durations EXACTLY as given (don't change any numbers)
- Add pitch before each number: "c2" not "2c"
- Duration 1 = just the letter (e.g., "c"), duration 2 = letter+2 (e.g., "c2")
- Separate notes with spaces, measures with |

Rhythm skeleton: {rhythm_output}

Output ABC notes only."""
        result_c = await run_agent_loop(
            client=client,
            system_prompt="You fill pitches into rhythm templates. Output only ABC notes.",
            user_message=fill_prompt,
            temperature=0.7,
            max_tool_calls=1,
            max_tokens=500,
        )
        two_pass_output = result_c.text.strip()
        print(f"Two-pass output: {two_pass_output[:200]}...")

        full_abc_c = f"X:1\nM:4/4\nL:1/8\nK:C\nV:1\n{two_pass_output}"
        c_result = validate_full_abc(full_abc_c)
        print(f"Passed: {c_result['passed']}, Failures: {c_result['fail_count']}")
        for m in c_result['measures']:
            if not m['ok']:
                print(f"  M{m['measure']}: {m['text'][:50]}... = {m['sum']} (off by {m['sum'] - TARGET_UNITS})")
    else:
        print("Rhythm skeleton had errors — cannot fill pitches. Two-pass approach would retry.")

    # Summary
    print("\n" + "=" * 60)
    print("RESULTS SUMMARY")
    print("=" * 60)
    a_status = "PASS" if validation_a["passed"] else f'FAIL ({validation_a["fail_count"]} measures)'
    b_status = "PASS" if b_result["passed"] else f'FAIL ({b_result["fail_count"]} measures)'
    print(f"  A (rhythm-only):    {a_status}")
    print(f"  B (single-pass):    {b_status}")
    if validation_a["passed"]:
        c_status = "PASS" if c_result["passed"] else f'FAIL ({c_result["fail_count"]} measures)'
        print(f"  C (two-pass):       {c_status}")
    else:
        print(f"  C (two-pass):       N/A (rhythm failed)")
    print("=" * 60)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true", help="Run parsing tests only")
    parser.add_argument("--live", action="store_true", help="Test against actual LLM")
    args = parser.parse_args()

    if args.live:
        asyncio.run(live_test())
    else:
        dry_run()
