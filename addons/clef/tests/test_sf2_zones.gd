extends SceneTree

func _init():
	var result := Sf2Reader.read_file("res://addons/clef/sound_front/GeneralUser-GS/GeneralUser-GS.sf2")
	if not result.ok:
		print("FAIL: ", result.error_message)
		quit()
		return
	
	var data: Sf2Data = result.data
	print("=== SF2 Loaded: %s ===" % data.bank_name)
	print("Instruments: %d, Samples: %d, Presets: %d" % [data.instruments.size(), data.samples.size(), data.presets.size()])
	
	# Find violin preset (preset 40, bank 0)
	var violin_preset: Sf2Data.Sf2Preset = null
	for p in data.presets:
		if p.preset_index == 40 and p.bank == 0:
			violin_preset = p
			break
	
	if violin_preset == null:
		print("FAIL: Violin preset (40) not found")
		quit()
		return
	
	print("\n=== Violin Preset: %s ===" % violin_preset.name)
	print("Zones: %d" % violin_preset.zones.size())
	for zi in range(violin_preset.zones.size()):
		var z: Sf2Data.Sf2PresetZone = violin_preset.zones[zi]
		print("  Zone %d: global=%s key=[%d,%d] vel=[%d,%d] inst=%d tune=%d+%d" % [
			zi, z.is_global, z.key_range.x, z.key_range.y,
			z.vel_range.x, z.vel_range.y, z.instrument_index,
			z.coarse_tune, z.fine_tune])
	
	# Get instrument referenced by first local zone
	var inst_idx := -1
	for z in violin_preset.zones:
		if not z.is_global:
			inst_idx = z.instrument_index
			break
	
	if inst_idx < 0 or inst_idx >= data.instruments.size():
		print("FAIL: Invalid instrument index")
		quit()
		return
	
	var inst: Sf2Data.Sf2Instrument = data.instruments[inst_idx]
	print("\n=== Instrument: %s (index=%d, zones=%d) ===" % [inst.name, inst_idx, inst.zones.size()])
	
	var global_count := 0
	var local_count := 0
	for zi in range(inst.zones.size()):
		var z: Sf2Data.Sf2InstrumentZone = inst.zones[zi]
		if z.sample_index >= 0:
			local_count += 1
			var sample: Sf2Data.Sf2SampleHeader = data.samples[z.sample_index] if z.sample_index < data.samples.size() else null
			var sname: String = sample.name if sample else "???"
			print("  LOCAL %d: key=[%d,%d] root=%d modes=%d sample=%d(%s) offsets=[%d,%d,%d,%d] adsr=[%.3f,%.3f,%.1f,%.3f] tune=%d" % [
				zi, z.key_range.x, z.key_range.y, z.root_key, z.sample_modes,
				z.sample_index, sname,
				z.start_offset, z.end_offset, z.loop_start_offset, z.loop_end_offset,
				z.attack, z.decay, z.sustain, z.release, z.tuning_cents])
		else:
			global_count += 1
			print("  GLOBAL %d: key=[%d,%d] modes=%d offsets=[%d,%d,%d,%d] adsr=[%.3f,%.3f,%.1f,%.3f]" % [
				zi, z.key_range.x, z.key_range.y, z.sample_modes,
				z.start_offset, z.end_offset, z.loop_start_offset, z.loop_end_offset,
				z.attack, z.decay, z.sustain, z.release])
	
	print("\nGlobal zones: %d, Local zones: %d" % [global_count, local_count])
	
	# Check if any local zone has sample_modes != -1
	var modes_ok := 0
	var modes_bad := 0
	for z in inst.zones:
		if z.sample_index >= 0:
			if z.sample_modes >= 0:
				modes_ok += 1
			else:
				modes_bad += 1
	print("Local zones with modes set: %d, modes=-1: %d" % [modes_ok, modes_bad])
	
	quit()
