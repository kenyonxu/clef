extends SceneTree

func _init():
	var result := Sf2Reader.read_file("res://addons/clef/sound_front/GeneralUser-GS/GeneralUser-GS.sf2")
	if not result.ok:
		print("FAIL: ", result.error_message)
		quit()
		return
	
	var data: Sf2Data = result.data
	
	# Check instrument 314
	var inst: Sf2Data.Sf2Instrument = data.instruments[314]
	print("=== Instrument 314: %s (zones=%d) ===" % [inst.name, inst.zones.size()])
	
	for zi in range(inst.zones.size()):
		var z: Sf2Data.Sf2InstrumentZone = inst.zones[zi]
		var is_local := z.sample_index >= 0
		var sample: Sf2Data.Sf2SampleHeader = data.samples[z.sample_index] if is_local and z.sample_index < data.samples.size() else null
		var sname: String = sample.name if sample else "N/A"
		var tag: String = "LOCAL" if is_local else "GLOBAL"
		print("  %s %d: key=[%d,%d] root=%d modes=%d sample=%d(%s) offsets=[%d,%d,%d,%d] adsr=[%.3f,%.3f,%.1f,%.3f]" % [
			tag, zi, z.key_range.x, z.key_range.y, z.root_key, z.sample_modes,
			z.sample_index, sname,
			z.start_offset, z.end_offset, z.loop_start_offset, z.loop_end_offset,
			z.attack, z.decay, z.sustain, z.release])
	
	# Now trace what sf2_bank would select for key=55, vel=100, ch=0
	print("\n=== Simulating sf2_bank.get_sample(40, 55, 100, 0) ===")
	
	# Find preset 40
	var preset: Sf2Data.Sf2Preset = null
	for p in data.presets:
		if p.preset_index == 40 and p.bank == 0:
			preset = p
			break
	
	# Simulate sf2_bank zone matching
	var _global_zone: Sf2Data.Sf2PresetZone = null
	var local_zones: Array = []
	for zone in preset.zones:
		if zone.is_global:
			_global_zone = zone
		else:
			local_zones.append(zone)
	
	var key := 55
	var vel := 100
	var best_zone = null
	for zone in local_zones:
		if key < zone.key_range.x or key > zone.key_range.y:
			continue
		if vel < zone.vel_range.x or vel > zone.vel_range.y:
			continue
		if best_zone == null:
			best_zone = zone
			continue
		var key_span: int = zone.key_range.y - zone.key_range.x
		var best_key_span: int = best_zone.key_range.y - best_zone.key_range.x
		if key_span < best_key_span:
			best_zone = zone
		elif key_span == best_key_span:
			var vel_span: int = zone.vel_range.y - zone.vel_range.x
			var best_vel_span: int = best_zone.vel_range.y - best_zone.vel_range.x
			if vel_span < best_vel_span:
				best_zone = zone
			elif vel_span == best_vel_span:
				best_zone = zone
	
	if best_zone:
		print("Best preset zone: inst=%d key=[%d,%d] vel=[%d,%d]" % [
			best_zone.instrument_index, best_zone.key_range.x, best_zone.key_range.y,
			best_zone.vel_range.x, best_zone.vel_range.y])
		var matched_inst: Sf2Data.Sf2Instrument = data.instruments[best_zone.instrument_index]
		print("Selected instrument: %s (index=%d)" % [matched_inst.name, best_zone.instrument_index])
		
		# Now simulate instrument zone matching
		var inst_global: Sf2Data.Sf2InstrumentZone = null
		var inst_locals: Array = []
		for zone in matched_inst.zones:
			if zone.sample_index < 0:
				inst_global = zone
			else:
				inst_locals.append(zone)
		
		var best_izone = null
		for zone in inst_locals:
			if key < zone.key_range.x or key > zone.key_range.y:
				continue
			if vel < zone.vel_range.x or vel > zone.vel_range.y:
				continue
			if best_izone == null:
				best_izone = zone
				continue
			var key_span2: int = zone.key_range.y - zone.key_range.x
			var best_key_span2: int = best_izone.key_range.y - best_izone.key_range.x
			if key_span2 < best_key_span2:
				best_izone = zone
			elif key_span2 == best_key_span2:
				var vel_span2: int = zone.vel_range.y - zone.vel_range.x
				var best_vel_span2: int = best_izone.vel_range.y - best_izone.vel_range.x
				if vel_span2 < best_vel_span2:
					best_izone = zone
				elif vel_span2 == best_vel_span2:
					best_izone = zone
		
		if best_izone:
			var sample2: Sf2Data.Sf2SampleHeader = data.samples[best_izone.sample_index]
			print("Best inst zone: key=[%d,%d] root=%d modes=%d sample=%d(%s)" % [
				best_izone.key_range.x, best_izone.key_range.y,
				best_izone.root_key, best_izone.sample_modes,
				best_izone.sample_index, sample2.name])
			print("Sample: start=%d end=%d loop=[%d,%d] rate=%d orig_pitch=%d pitch_corr=%d" % [
				sample2.start, sample2.end, sample2.loop_start, sample2.loop_end,
				sample2.sample_rate, sample2.original_pitch, sample2.pitch_correction])
			var sample_frames := sample2.end - sample2.start
			var loop_frames := sample2.loop_end - sample2.loop_start
			print("Sample frames: %d (%.1fms), Loop frames: %d (%.1fms)" % [
				sample_frames, float(sample_frames) / 44100.0 * 1000.0,
				loop_frames, float(loop_frames) / 44100.0 * 1000.0])
			print("Has valid loop: %s (loop_end > loop_start + 64 = %s)" % [
				"YES" if sample2.loop_end > sample2.loop_start + 64 else "NO",
				"YES" if loop_frames > 64 else "NO"])
	
	quit()
