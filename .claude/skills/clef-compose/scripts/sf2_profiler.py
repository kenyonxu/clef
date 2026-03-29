"""SF2 Profiler — 分析 SoundFont 2 文件，生成作曲友好的 JSON profile。

输出每个 Preset 的关键参数：key_range, sweet_spot, vel_layers,
avg_attack/release, quality 等，供 Clef Compose Agent 使用。

用法:
    python sf2_profiler.py <sf2_path> -o <output.json>
    python sf2_profiler.py <sf2_path> --list
    python sf2_profiler.py <sf2_path> -o <output.json> --presets 0,48,73
"""

from __future__ import annotations

import argparse
import json
import struct
import sys
from dataclasses import dataclass, field
from pathlib import Path


# ---------------------------------------------------------------------------
# SF2 Generator 类型 ID
# ---------------------------------------------------------------------------
GEN_KEY_RANGE = 43
GEN_VEL_RANGE = 44
GEN_SAMPLE_ID = 53
GEN_OVERRIDING_ROOT_KEY = 58
GEN_ATTACK_VOL_ENV = 34
GEN_HOLD_VOL_ENV = 35
GEN_DECAY_VOL_ENV = 36
GEN_SUSTAIN_VOL_ENV = 37
GEN_RELEASE_VOL_ENV = 38
GEN_INITIAL_ATTENUATION = 48
GEN_INSTRUMENT = 41
GEN_END_OF_GENERATORS = 60
GEN_SAMPLE_MODES = 54
GEN_COARSE_TUNE = 51
GEN_FINE_TUNE = 52


# ---------------------------------------------------------------------------
# 数据结构
# ---------------------------------------------------------------------------
@dataclass
class SampleHeader:
    name: str = ""
    start: int = 0
    end: int = 0
    loop_start: int = 0
    loop_end: int = 0
    sample_rate: int = 44100
    original_pitch: int = 60
    pitch_correction: int = 0
    sample_type: int = 1
    link_index: int = 0


@dataclass
class InstrumentZone:
    key_range: tuple[int, int] = (0, 127)
    vel_range: tuple[int, int] = (0, 127)
    sample_index: int = -1
    root_key: int = -1
    tuning_cents: int = 0
    attack: float = -1.0
    hold: float = -1.0
    decay: float = -1.0
    sustain: float = -1.0
    release: float = -1.0
    is_global: bool = False


@dataclass
class Instrument:
    name: str = ""
    zones: list[InstrumentZone] = field(default_factory=list)


@dataclass
class PresetZone:
    key_range: tuple[int, int] = (0, 127)
    vel_range: tuple[int, int] = (0, 127)
    instrument_index: int = -1
    coarse_tune: int = 0
    fine_tune: int = 0
    is_global: bool = False


@dataclass
class Preset:
    name: str = ""
    preset_index: int = 0
    bank: int = 0
    zones: list[PresetZone] = field(default_factory=list)


# ---------------------------------------------------------------------------
# SF2 二进制解析
# ---------------------------------------------------------------------------
class Sf2Parser:
    """纯 Python SF2 解析器，只读取 pdta 块（跳过 sdta 采样数据以节省内存）。"""

    def __init__(self, data: bytes):
        self._data = data
        self._pos = 0

    def _read(self, fmt: str) -> tuple:
        size = struct.calcsize(fmt)
        values = struct.unpack_from('<' + fmt, self._data, self._pos)
        self._pos += size
        return values

    def _read_u16(self) -> int:
        return self._read('H')[0]

    def _read_u32(self) -> int:
        return self._read('I')[0]

    def _read_i16(self) -> int:
        return self._read('h')[0]

    def _read_string(self, length: int) -> str:
        raw = self._data[self._pos:self._pos + length]
        self._pos += length
        return raw.split(b'\x00')[0].decode('ascii', errors='replace').strip()

    def parse(self) -> dict:
        """解析 SF2，返回 {presets, instruments, samples, info}。"""
        # RIFF header
        riff_id = self._read_string(4)
        if riff_id != 'RIFF':
            raise ValueError("Not a RIFF file")
        _file_size = self._read_u32()
        form_type = self._read_string(4)
        if form_type != 'sfbk':
            raise ValueError("Not an SF2 file")

        info = {}
        samples: list[SampleHeader] = []
        presets: list[Preset] = []
        instruments: list[Instrument] = []

        # Parse top-level chunks
        while self._pos < len(self._data) - 8:
            chunk_id = self._read_string(4)
            chunk_size = self._read_u32()
            if self._pos + chunk_size > len(self._data):
                break
            chunk_data = self._data[self._pos:self._pos + chunk_size]
            self._pos += chunk_size

            if chunk_id == 'LIST':
                list_type = chunk_data[:4].decode('ascii', errors='replace')
                if list_type == 'INFO':
                    info = self._parse_info(chunk_data[4:])
                elif list_type == 'pdta':
                    pdta = self._parse_pdta(chunk_data[4:])
                    samples = pdta['samples']
                    presets = pdta['presets']
                    instruments = pdta['instruments']

        return {'presets': presets, 'instruments': instruments, 'samples': samples, 'info': info}

    def _parse_info(self, data: bytes) -> dict:
        info = {}
        pos = 0
        while pos + 8 <= len(data):
            sub_id = data[pos:pos + 4].decode('ascii', errors='replace').lower()
            sub_size = struct.unpack_from('<I', data, pos + 4)[0]
            sub_data = data[pos + 8:pos + 8 + sub_size]
            pos += 8 + sub_size
            if sub_id == 'ifil' and sub_size >= 4:
                major, minor = struct.unpack_from('<HH', sub_data)
                info['version'] = f"{major}.{minor:02d}"
            elif sub_id == 'isng':
                info['sound_engine'] = sub_data.split(b'\x00')[0].decode('ascii', errors='replace').strip()
            elif sub_id == 'inam':
                info['name'] = sub_data.split(b'\x00')[0].decode('ascii', errors='replace').strip()
        return info

    def _parse_pdta(self, data: bytes) -> dict:
        """解析 pdta 块中的 9 个子块。"""
        subchunks: dict[str, bytes] = {}
        expected = [b'phdr', b'pbag', b'pmod', b'pgen',
                    b'inst', b'ibag', b'imod', b'igen', b'shdr']
        pos = 0
        idx = 0
        while pos + 8 <= len(data) and idx < len(expected):
            sub_id = data[pos:pos + 4]
            sub_size = struct.unpack_from('<I', data, pos + 4)[0]
            sub_data = data[pos + 8:pos + 8 + sub_size]
            pos += 8 + sub_size
            if sub_id in expected:
                subchunks[sub_id.decode('ascii')] = sub_data
            idx += 1

        # Parse sample headers first (needed by instruments)
        samples = self._parse_shdr(subchunks.get('shdr', b''))

        # Parse presets
        presets = self._parse_presets(
            subchunks.get('phdr', b''),
            subchunks.get('pbag', b''),
            subchunks.get('pgen', b''),
        )

        # Parse instruments
        instruments = self._parse_instruments(
            subchunks.get('inst', b''),
            subchunks.get('ibag', b''),
            subchunks.get('igen', b''),
        )

        return {'presets': presets, 'instruments': instruments, 'samples': samples}

    def _parse_shdr(self, data: bytes) -> list[SampleHeader]:
        if len(data) < 46:
            return []
        record_size = 46
        count = len(data) // record_size
        samples = []
        for i in range(max(0, count - 1)):  # Skip terminator
            s = SampleHeader()
            pos = i * record_size
            s.name = data[pos:pos + 20].split(b'\x00')[0].decode('ascii', errors='replace').strip()
            s.start, s.end, s.loop_start, s.loop_end, s.sample_rate = struct.unpack_from('<IIIII', data, pos + 20)
            s.original_pitch = data[pos + 40]
            s.pitch_correction = struct.unpack_from('<b', data, pos + 41)[0]
            s.sample_type, s.link_index = struct.unpack_from('<HH', data, pos + 42)
            samples.append(s)
        return samples

    def _read_bags(self, data: bytes) -> list[tuple[int, int]]:
        bags = []
        for i in range(len(data) // 4):
            pos = i * 4
            gen_ndx, mod_ndx = struct.unpack_from('<HH', data, pos)
            bags.append((gen_ndx, mod_ndx))
        return bags

    def _read_gens(self, data: bytes) -> list[tuple[int, int, int]]:
        """返回 [(type_id, unsigned_value, signed_value), ...]"""
        gens = []
        for i in range(len(data) // 4):
            pos = i * 4
            type_id, raw = struct.unpack_from('<HH', data, pos)
            signed = raw if raw <= 32767 else raw - 65536
            gens.append((type_id, raw, signed))
        return gens

    def _parse_presets(self, phdr_data: bytes, pbag_data: bytes, pgen_data: bytes) -> list[Preset]:
        if len(phdr_data) < 38:
            return []
        record_size = 38
        count = len(phdr_data) // record_size

        # Pre-read headers
        headers = []
        for i in range(count):
            pos = i * record_size
            name = phdr_data[pos:pos + 20].split(b'\x00')[0].decode('ascii', errors='replace').strip()
            preset, bank, bag_index = struct.unpack_from('<HHH', phdr_data, pos + 20)
            headers.append((name, preset, bank, bag_index))

        bags = self._read_bags(pbag_data)
        gens = self._read_gens(pgen_data)

        presets = []
        for i in range(max(0, count - 1)):
            name, preset_idx, bank, start_bag = headers[i]
            end_bag = headers[i + 1][3] if i + 1 < len(headers) else len(bags)

            preset = Preset(name=name, preset_index=preset_idx, bank=bank)
            for bag_i in range(start_bag, end_bag):
                if bag_i >= len(bags):
                    break
                gen_start = bags[bag_i][0]
                gen_end = bags[bag_i + 1][0] if bag_i + 1 < len(bags) else len(gens)

                zone = PresetZone()
                has_instrument = False
                for gen_i in range(gen_start, gen_end):
                    if gen_i >= len(gens):
                        break
                    gtype, gval, gsval = gens[gen_i]
                    if gtype == GEN_END_OF_GENERATORS:
                        break
                    elif gtype == GEN_KEY_RANGE:
                        zone.key_range = (gval & 0xFF, (gval >> 8) & 0xFF)
                    elif gtype == GEN_VEL_RANGE:
                        zone.vel_range = (gval & 0xFF, (gval >> 8) & 0xFF)
                    elif gtype == GEN_INSTRUMENT:
                        has_instrument = True
                        zone.instrument_index = gval
                    elif gtype == GEN_COARSE_TUNE:
                        zone.coarse_tune = gsval
                    elif gtype == GEN_FINE_TUNE:
                        zone.fine_tune = gsval

                zone.is_global = not has_instrument
                preset.zones.append(zone)

            presets.append(preset)
        return presets

    def _parse_instruments(self, inst_data: bytes, ibag_data: bytes, igen_data: bytes) -> list[Instrument]:
        if len(inst_data) < 22:
            return []
        record_size = 22
        count = len(inst_data) // record_size

        headers = []
        for i in range(count):
            pos = i * record_size
            name = inst_data[pos:pos + 20].split(b'\x00')[0].decode('ascii', errors='replace').strip()
            bag_index = struct.unpack_from('<H', inst_data, pos + 20)[0]
            headers.append((name, bag_index))

        bags = self._read_bags(ibag_data)
        gens = self._read_gens(igen_data)

        instruments = []
        for i in range(max(0, count - 1)):
            name, start_bag = headers[i]
            end_bag = headers[i + 1][1] if i + 1 < len(headers) else len(bags)

            inst = Instrument(name=name)
            for bag_i in range(start_bag, end_bag):
                if bag_i >= len(bags):
                    break
                gen_start = bags[bag_i][0]
                gen_end = bags[bag_i + 1][0] if bag_i + 1 < len(bags) else len(gens)

                zone = InstrumentZone()
                has_sample = False
                for gen_i in range(gen_start, gen_end):
                    if gen_i >= len(gens):
                        break
                    gtype, gval, gsval = gens[gen_i]
                    if gtype == GEN_END_OF_GENERATORS:
                        break
                    elif gtype == GEN_KEY_RANGE:
                        zone.key_range = (gval & 0xFF, (gval >> 8) & 0xFF)
                    elif gtype == GEN_VEL_RANGE:
                        zone.vel_range = (gval & 0xFF, (gval >> 8) & 0xFF)
                    elif gtype == GEN_SAMPLE_ID:
                        has_sample = True
                        zone.sample_index = gval
                    elif gtype == GEN_OVERRIDING_ROOT_KEY:
                        zone.root_key = gval
                    elif gtype == GEN_FINE_TUNE:
                        zone.tuning_cents += gsval
                    elif gtype == GEN_COARSE_TUNE:
                        zone.tuning_cents += gsval * 100
                    elif gtype == GEN_ATTACK_VOL_ENV:
                        zone.attack = _timecent_to_seconds(gsval)
                    elif gtype == GEN_HOLD_VOL_ENV:
                        zone.hold = _timecent_to_seconds(gsval)
                    elif gtype == GEN_DECAY_VOL_ENV:
                        zone.decay = _timecent_to_seconds(gsval)
                    elif gtype == GEN_SUSTAIN_VOL_ENV:
                        zone.sustain = _centibels_to_linear(gsval)
                    elif gtype == GEN_RELEASE_VOL_ENV:
                        zone.release = _timecent_to_seconds(gsval)

                zone.is_global = not has_sample
                inst.zones.append(zone)

            instruments.append(inst)
        return instruments


# ---------------------------------------------------------------------------
# 辅助转换
# ---------------------------------------------------------------------------
def _timecent_to_seconds(tc: int) -> float:
    if tc == 32767 or tc == -32768:
        return -1.0
    # Cap at reasonable range: values > 10000 timecents produce >60s (unrealistic)
    if tc > 10000:
        return -1.0  # Treat as "not set"
    return 2.0 ** (float(tc) / 1200.0)


def _centibels_to_linear(cb: int) -> float:
    if cb == 32767 or cb == -32768:
        return -1.0
    return 10.0 ** (-float(cb) / 200.0)


# ---------------------------------------------------------------------------
# Profile 生成
# ---------------------------------------------------------------------------
def _compute_sweet_spot(inst_zones: list[InstrumentZone]) -> tuple[int, int]:
    """基于 zone 密度计算 sweet_spot（覆盖密度最高的连续 2 个八度区间）。

    当密度分布均匀时，取 key 范围中间 2 个八度（音色最佳区域通常在中音区）。
    """
    # Count how many zones cover each MIDI key
    coverage = [0] * 128
    for z in inst_zones:
        if z.is_global:
            continue
        lo, hi = z.key_range
        for k in range(max(0, lo), min(128, hi + 1)):
            coverage[k] += 1

    # Find densest 24-key window (2 octaves)
    best_start = 0
    best_score = -1
    all_scores = []
    for start in range(0, 128 - 24):
        score = sum(coverage[start:start + 24])
        all_scores.append(score)
        if score > best_score:
            best_score = score
            best_start = start

    # Check if coverage is relatively uniform (best < 2x average)
    active_keys = [k for k in range(128) if coverage[k] > 0]
    if active_keys:
        avg_score = sum(all_scores) / len(all_scores) if all_scores else 0
        if best_score <= avg_score * 1.5 or avg_score < 1:
            # Uniform distribution: use center of active range
            center = (active_keys[0] + active_keys[-1]) // 2
            best_start = max(0, min(center - 12, 128 - 24))

    return (best_start, best_start + 23)


def _count_vel_layers(inst_zones: list[InstrumentZone]) -> int:
    """估算 velocity layers：对每个 MIDI key，统计有多少个不同 vel_range 的 zone 覆盖它。

    取所有 key 中的最大重叠数作为 vel_layers（即最精细力度的区域）。
    """
    max_layers = 1
    for key in range(128):
        vel_ranges_at_key = set()
        for z in inst_zones:
            if z.is_global or z.sample_index < 0:
                continue
            lo, hi = z.key_range
            if lo <= key <= hi:
                vel_ranges_at_key.add(z.vel_range)
        if len(vel_ranges_at_key) > max_layers:
            max_layers = len(vel_ranges_at_key)
    return max_layers


def _quality_score(inst_zones: list[InstrumentZone], vel_layers: int) -> str:
    """启发式质量评分。"""
    zone_count = sum(1 for z in inst_zones if not z.is_global and z.sample_index >= 0)
    unique_samples = len(set(z.sample_index for z in inst_zones if not z.is_global and z.sample_index >= 0))
    score = zone_count * 2 + vel_layers * 3 + unique_samples
    if score >= 15:
        return "high"
    elif score >= 8:
        return "medium"
    return "low"


def _derive_characteristics(
    avg_attack: float,
    avg_release: float,
    inst_zones: list[InstrumentZone],
) -> list[str]:
    """从 ADSR 参数推导音色特征。"""
    chars = []
    if avg_attack >= 0 and avg_attack > 0.15:
        chars.append("slow_attack")
    elif avg_attack >= 0 and avg_attack <= 0.01:
        chars.append("percussive")
    if avg_release >= 0 and avg_release > 1.5:
        chars.append("long_release")
    if avg_release >= 0 and avg_release < 0.2:
        chars.append("short_release")
    # Check if instrument has loop (sustained sound)
    has_loop = any(
        z.sample_modes == 1 or z.sample_modes == 3
        for z in inst_zones
        if hasattr(z, 'sample_modes')
    )
    if has_loop:
        chars.append("sustained")
    return chars


def build_profile(
    presets: list[Preset],
    instruments: list[Instrument],
    info: dict,
    filter_presets: set[int] | None = None,
) -> dict:
    """从解析数据生成 composer-friendly profile。"""
    result = {
        "sf2_name": info.get('name', 'Unknown'),
        "version": info.get('version', ''),
        "sound_engine": info.get('sound_engine', ''),
        "preset_count": len(presets),
        "presets": {},
    }

    for preset in presets:
        if filter_presets is not None and preset.preset_index not in filter_presets:
            continue
        if preset.bank != 0:
            continue  # Only use bank 0 (standard GM)

        # Collect all instrument zones referenced by this preset
        all_inst_zones: list[InstrumentZone] = []
        for pz in preset.zones:
            if pz.is_global or pz.instrument_index < 0 or pz.instrument_index >= len(instruments):
                continue
            inst = instruments[pz.instrument_index]
            all_inst_zones.extend(inst.zones)

        non_global_zones = [z for z in all_inst_zones if not z.is_global and z.sample_index >= 0]
        if not non_global_zones:
            continue

        # Aggregate key_range across all preset zones
        kr_lo = min(pz.key_range[0] for pz in preset.zones if not pz.is_global)
        kr_hi = max(pz.key_range[1] for pz in preset.zones if not pz.is_global)

        # Aggregate vel_range
        vr_lo = min(pz.vel_range[0] for pz in preset.zones if not pz.is_global)
        vr_hi = max(pz.vel_range[1] for pz in preset.zones if not pz.is_global)

        # Compute metrics
        sweet_spot = _compute_sweet_spot(non_global_zones)
        vel_layers = _count_vel_layers(non_global_zones)
        quality = _quality_score(non_global_zones, vel_layers)

        # Average ADSR
        attacks = [z.attack for z in non_global_zones if z.attack >= 0]
        releases = [z.release for z in non_global_zones if z.release >= 0]
        avg_attack = sum(attacks) / len(attacks) if attacks else -1.0
        avg_release = sum(releases) / len(releases) if releases else -1.0

        characteristics = _derive_characteristics(avg_attack, avg_release, non_global_zones)

        # Map preset index to a GM name hint
        gm_name = _preset_to_gm_name(preset.preset_index)

        result['presets'][str(preset.preset_index)] = {
            "name": preset.name,
            "gm_name": gm_name,
            "key_range": [kr_lo, kr_hi],
            "vel_range": [vr_lo, vr_hi],
            "sweet_spot": list(sweet_spot),
            "vel_layers": vel_layers,
            "avg_attack": round(avg_attack, 4),
            "avg_release": round(avg_release, 4),
            "quality": quality,
            "characteristics": characteristics,
        }

    return result


def _preset_to_gm_name(preset_index: int) -> str:
    """映射常见 GM preset 编号到简短名称。"""
    mapping = {
        0: "piano", 1: "bright_piano", 2: "electric_grand", 3: "honkytonk_piano",
        4: "electric_piano1", 5: "electric_piano2", 6: "harpsichord", 7: "clavinet",
        8: "celesta", 9: "glockenspiel", 10: "music_box", 11: "vibraphone",
        12: "marimba", 13: "xylophone", 14: "tubular_bell", 15: "dulcimer",
        16: "drawbar_organ", 17: "percussive_organ", 18: "rock_organ", 19: "church_organ",
        20: "reed_organ", 21: "accordion", 22: "harmonica", 23: "tango_accordion",
        24: "acoustic_guitar", 25: "steel_guitar", 26: "jazz_guitar", 27: "clean_guitar",
        28: "muted_guitar", 29: "overdriven_guitar", 30: "distortion_guitar",
        31: "guitar_harmonics", 32: "acoustic_bass", 33: "electric_bass_finger",
        34: "electric_bass_pick", 35: "fretless_bass", 36: "slap_bass1",
        37: "slap_bass2", 38: "synth_bass1", 39: "synth_bass2",
        40: "violin", 41: "viola", 42: "cello", 43: "contrabass",
        44: "tremolo_strings", 45: "pizzicato_strings", 46: "orchestral_harp",
        47: "timpani", 48: "strings", 49: "slow_strings",
        50: "synth_strings1", 51: "synth_strings2", 52: "choir_aahs",
        53: "voice_oohs", 54: "synth_choir", 55: "orchestra_hit",
        56: "trumpet", 57: "trombone", 58: "tuba", 59: "muted_trumpet",
        60: "french_horn", 61: "brass_section", 62: "synth_brass1", 63: "synth_brass2",
        64: "soprano_sax", 65: "alto_sax", 66: "tenor_sax", 67: "baritone_sax",
        68: "oboe", 69: "english_horn", 70: "bassoon", 71: "clarinet",
        72: "piccolo", 73: "flute", 74: "recorder", 75: "pan_flute",
        76: "bottle_blow", 77: "shakuhachi", 78: "whistle", 79: "ocarina",
        80: "synth_lead_square", 81: "synth_lead_saw", 82: "synth_lead_calliope",
        83: "synth_lead_chiff", 84: "synth_lead_charang", 85: "synth_lead_voice",
        86: "synth_lead_fifths", 87: "synth_lead_bass_lead",
        88: "synth_pad_new_age", 89: "synth_pad_warm", 90: "synth_pad_polysynth",
        91: "synth_pad_choir", 92: "synth_pad_bowed", 93: "synth_pad_metallic",
        94: "synth_pad_halo", 95: "synth_pad_sweep",
    }
    return mapping.get(preset_index, f"gm_{preset_index}")


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------
def main():
    parser = argparse.ArgumentParser(description='SF2 Profiler — 生成作曲友好的 JSON profile')
    parser.add_argument('sf2_path', type=Path, help='SF2 文件路径')
    parser.add_argument('-o', '--output', type=Path, default=None, help='输出 JSON 路径')
    parser.add_argument('--list', action='store_true', help='列出所有 preset 名称')
    parser.add_argument('--presets', type=str, default=None,
                        help='只分析指定的 preset 索引（逗号分隔，如 0,48,73）')
    args = parser.parse_args()

    if not args.sf2_path.exists():
        print(f"错误: 文件不存在 {args.sf2_path}", file=sys.stderr)
        sys.exit(1)

    print(f"正在解析 {args.sf2_path.name} ...", file=sys.stderr)
    raw = args.sf2_path.read_bytes()
    parser_instance = Sf2Parser(raw)
    result = parser_instance.parse()

    presets = result['presets']
    instruments = result['instruments']
    info = result['info']

    print(f"  音色库名: {info.get('name', 'Unknown')}", file=sys.stderr)
    print(f"  版本: {info.get('version', '?')}", file=sys.stderr)
    print(f"  Presets: {len(presets)}", file=sys.stderr)
    print(f"  Instruments: {len(instruments)}", file=sys.stderr)

    if args.list:
        for p in presets:
            bank_tag = f"[Bank {p.bank}] " if p.bank != 0 else ""
            zone_count = sum(1 for z in p.zones if not z.is_global)
            print(f"  {p.preset_index:3d}: {bank_tag}{p.name} ({zone_count} zones)")
        return

    filter_presets = None
    if args.presets:
        filter_presets = set(int(x.strip()) for x in args.presets.split(','))

    profile = build_profile(presets, instruments, info, filter_presets)

    json_str = json.dumps(profile, indent=2, ensure_ascii=False)

    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json_str, encoding='utf-8')
        print(f"已写入 {args.output} ({len(json_str)} bytes)", file=sys.stderr)
    else:
        print(json_str)


if __name__ == '__main__':
    main()
