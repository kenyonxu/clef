import struct, os, sys, math
sys.stdout.reconfigure(encoding='utf-8')

def parse_midi(path):
    with open(path,'rb') as f: data = f.read()
    tracks = struct.unpack_from('>h', data, 10)[0]
    div = struct.unpack_from('>h', data, 12)[0]
    pos = 14
    all_events = []
    for t in range(tracks):
        if pos+4 > len(data) or data[pos:pos+4] != b'MTrk': break
        tlen = struct.unpack_from('>I', data, pos+4)[0]
        td = data[pos+8:pos+8+tlen]
        p = 0; tick = 0; rs = 0
        while p < len(td):
            delta = 0
            while p < len(td):
                b = td[p]; p += 1
                delta = (delta << 7) | (b & 0x7F)
                if b < 0x80: break
            tick += delta
            if p >= len(td): break
            ev = td[p]
            if ev >= 0x80: status = ev; p += 1
            else: status = rs
            rs = status
            mt = status & 0xF0; ch = status & 0x0F
            if mt == 0x90 and p+1 < len(td):
                note = td[p]; vel = td[p+1]; p += 2
                if vel > 0: all_events.append((tick, note, vel, ch))
            elif mt == 0x80 and p+1 < len(td): p += 2
            elif mt in (0xA0,0xB0,0xE0): p += 2
            elif mt in (0xC0,0xD0): p += 1
            elif mt == 0xF0:
                if status == 0xFF:
                    if p < len(td): p += 1
                    ml = 0
                    while p < len(td):
                        b = td[p]; p += 1
                        ml = (ml << 7) | (b & 0x7F)
                        if b < 0x80: break
                    p += ml
                elif status in (0xF0, 0xF7):
                    while p < len(td):
                        b = td[p]; p += 1
                        if b == 0xF7: break
        pos += 8 + tlen
    return all_events, div

def analyze(path):
    events, div = parse_midi(path)
    if not events: return None
    ch_events = {}
    for ev in events:
        t, n, v, c = ev
        if c == 9: continue
        if c not in ch_events: ch_events[c] = []
        ch_events[c].append((t, n, v))
    for c in ch_events: ch_events[c].sort()
    total_ticks = max(ev[0] for ev in events)
    total_notes = len(events)
    melody_ch = min(ch_events.keys()) if ch_events else 0
    mel = sorted(ch_events.get(melody_ch, []))
    total_beats = total_ticks / div if div > 0 else 1
    notes_per_beat = total_notes / total_beats if total_beats > 0 else 0
    unique_pitches = len(set(ev[1] for ev in events))
    pitch_entropy = 0
    pitch_counts = {}
    for ev in events:
        pitch_counts[ev[1]] = pitch_counts.get(ev[1], 0) + 1
    for c in pitch_counts.values():
        p = c / total_notes
        if p > 0: pitch_entropy -= p * math.log2(p)
    mid = total_ticks // 2
    first_pitches = set(n for t,n,_ in events if t <= mid)
    second_pitches = set(n for t,n,_ in events if t > mid)
    overlap = len(first_pitches & second_pitches) / max(len(first_pitches | second_pitches), 1)
    ch_ranges = {}
    for c, evts in ch_events.items():
        if evts:
            pitches = [n for _,n,_ in evts]
            ch_ranges[c] = (min(pitches), max(pitches))
    overlaps = 0
    chs = list(ch_ranges.keys())
    for i in range(len(chs)):
        for j in range(i+1, len(chs)):
            lo = max(ch_ranges[chs[i]][0], ch_ranges[chs[j]][0])
            hi = min(ch_ranges[chs[i]][1], ch_ranges[chs[j]][1])
            if hi > lo: overlaps += (hi - lo)
    large_jumps = 0
    for i in range(1, len(mel)):
        if abs(mel[i][1] - mel[i-1][1]) > 7: large_jumps += 1
    jump_rate = large_jumps / max(len(mel)-1, 1)
    first_vel = [v for t,_,v in mel if t <= mid]
    second_vel = [v for t,_,v in mel if t > mid]
    first_avg_vel = sum(first_vel)/len(first_vel) if first_vel else 0
    second_avg_vel = sum(second_vel)/len(second_vel) if second_vel else 0
    vel_arc = second_avg_vel - first_avg_vel
    first_p = [n for t,n,_ in mel if t <= mid]
    second_p = [n for t,n,_ in mel if t > mid]
    pitch_arc = (sum(second_p)/max(len(second_p),1) - sum(first_p)/max(len(first_p),1))
    mel_pitches = [n for _,n,_ in mel]
    mel_pitch_counts = {}
    for n in mel_pitches: mel_pitch_counts[n] = mel_pitch_counts.get(n, 0) + 1
    top3 = sum(sorted(mel_pitch_counts.values(), reverse=True)[:3]) / max(len(mel_pitches), 1)
    vels = [v for _,_,v in mel]
    vel_mean = sum(vels)/len(vels) if vels else 0
    vel_std = (sum((v-vel_mean)**2 for v in vels)/len(vels))**0.5 if vels else 0
    iois = []
    for i in range(1, len(mel)):
        ioi = mel[i][0] - mel[i-1][0]
        if ioi > 0: iois.append(ioi)
    ioi_std = (sum((i - sum(iois)/len(iois))**2 for i in iois)/len(iois))**0.5 if len(iois) > 1 else 0
    ioi_cv = ioi_std / (sum(iois)/len(iois)) if iois and sum(iois)/len(iois) > 0 else 0
    return {
        'notes_per_beat': notes_per_beat, 'unique_pitches': unique_pitches,
        'pitch_entropy': pitch_entropy, 'repetition_overlap': overlap,
        'channel_overlap_semitones': overlaps, 'large_jump_rate': jump_rate,
        'vel_arc': vel_arc, 'pitch_arc': pitch_arc, 'top3_dominance': top3,
        'vel_std': vel_std, 'ioi_cv': ioi_cv, 'total_notes': total_notes,
        'melody_notes': len(mel), 'total_beats': total_beats,
    }

base = 'e:/GitHub/clef-dev/addons/clef/output'
files = sorted([f for f in os.listdir(base) if f.endswith('_final.mid') and not f.startswith('.')])

for f in files:
    path = os.path.join(base, f)
    r = analyze(path)
    if r is None: continue
    name = f.replace('_final.mid','')
    boring = 'SEVERE' if r['notes_per_beat'] < 1.5 else ('WARN' if r['notes_per_beat'] < 3 else 'OK')
    rep = 'SEVERE' if r['repetition_overlap'] > 0.8 else ('WARN' if r['repetition_overlap'] > 0.6 else 'OK')
    noisy = 'SEVERE' if r['channel_overlap_semitones'] > 20 else ('WARN' if r['channel_overlap_semitones'] > 10 else 'OK')
    weird = 'SEVERE' if r['large_jump_rate'] > 0.15 else ('WARN' if r['large_jump_rate'] > 0.08 else 'OK')
    no_climax = 'SEVERE' if (r['vel_arc'] < -5 and r['pitch_arc'] < -2) else ('WARN' if (r['vel_arc'] < 2 and r['pitch_arc'] < 1) else 'OK')
    unmemorable = 'SEVERE' if r['top3_dominance'] > 0.55 else ('WARN' if r['top3_dominance'] > 0.40 else 'OK')
    robotic = 'SEVERE' if (r['vel_std'] < 5 and r['ioi_cv'] < 0.2) else ('WARN' if (r['vel_std'] < 12 and r['ioi_cv'] < 0.4) else 'OK')
    issues = [k for k,v in [('boring',boring),('rep',rep),('noisy',noisy),('weird',weird),('no_climax',no_climax),('unmemorable',unmemorable),('robotic',robotic)] if v != 'OK']
    print(f'=== {name} ({r["total_beats"]:.0f} beats, {r["total_notes"]} notes) ===')
    print(f'  boring:     {boring}  (npb={r["notes_per_beat"]:.2f}, H={r["pitch_entropy"]:.2f})')
    print(f'  repetitive: {rep}  (overlap={r["repetition_overlap"]:.0%})')
    print(f'  noisy:      {noisy}  (overlap={r["channel_overlap_semitones"]:.0f}st)')
    print(f'  weird:      {weird}  (jump_rate={r["large_jump_rate"]:.0%})')
    print(f'  no_climax:  {no_climax}  (vel={r["vel_arc"]:+.1f}, pitch={r["pitch_arc"]:+.1f})')
    print(f'  unmemorable: {unmemorable}  (top3={r["top3_dominance"]:.0%})')
    print(f'  robotic:    {robotic}  (vel_std={r["vel_std"]:.1f}, ioi_cv={r["ioi_cv"]:.2f})')
    if issues: print(f'  >> ISSUES: {", ".join(issues)}')
    print()
