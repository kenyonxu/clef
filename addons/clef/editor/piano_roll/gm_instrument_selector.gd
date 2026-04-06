## 音色选择弹窗
## 优先显示 SF2 实际音色，未加载时 fallback GM 硬编码
extends AcceptDialog

signal instrument_selected(preset: int)

const GM_NAMES: PackedStringArray = [
	"Acoustic Grand Piano", "Bright Acoustic Piano", "Electric Grand Piano", "Honky-tonk Piano",
	"Electric Piano 1", "Electric Piano 2", "Harpsichord", "Clavinet",
	"Celesta", "Glockenspiel", "Music Box", "Vibraphone",
	"Marimba", "Xylophone", "Tubular Bells", "Dulcimer",
	"Drawbar Organ", "Percussive Organ", "Rock Organ", "Church Organ",
	"Reed Organ", "Accordion", "Harmonica", "Tango Accordion",
	"Nylon Guitar", "Steel Guitar", "Jazz Guitar", "Clean Guitar",
	"Muted Guitar", "Overdriven Guitar", "Distortion Guitar", "Guitar Harmonics",
	"Acoustic Bass", "Finger Bass", "Pick Bass", "Fretless Bass",
	"Slap Bass 1", "Slap Bass 2", "Synth Bass 1", "Synth Bass 2",
	"Violin", "Viola", "Cello", "Contrabass",
	"Tremolo Strings", "Pizzicato Strings", "Orchestral Harp", "Timpani",
	"String Ensemble 1", "String Ensemble 2", "Synth Strings 1", "Synth Strings 2",
	"Choir Aahs", "Voice Oohs", "Synth Choir", "Orchestra Hit",
	"Trumpet", "Trombone", "Tuba", "Muted Trumpet",
	"French Horn", "Brass Section", "Synth Brass 1", "Synth Brass 2",
	"Soprano Sax", "Alto Sax", "Tenor Sax", "Baritone Sax",
	"Oboe", "English Horn", "Bassoon", "Clarinet",
	"Piccolo", "Flute", "Recorder", "Pan Flute",
	"Blown Bottle", "Shakuhachi", "Whistle", "Ocarina",
	"Lead 1 (square)", "Lead 2 (sawtooth)", "Lead 3 (calliope)", "Lead 4 (chiff)",
	"Lead 5 (charang)", "Lead 6 (voice)", "Lead 7 (fifths)", "Lead 8 (bass+lead)",
	"Pad 1 (new age)", "Pad 2 (warm)", "Pad 3 (polysynth)", "Pad 4 (choir)",
	"Pad 5 (bowed)", "Pad 6 (metallic)", "Pad 7 (halo)", "Pad 8 (sweep)",
	"FX 1 (rain)", "FX 2 (soundtrack)", "FX 3 (crystal)", "FX 4 (atmosphere)",
	"FX 5 (brightness)", "FX 6 (goblins)", "FX 7 (echoes)", "FX 8 (sci-fi)",
	"Sitar", "Banjo", "Shamisen", "Koto",
	"Kalimba", "Bagpipe", "Fiddle", "Shanai",
	"Tinkle Bell", "Agogo", "Steel Drums", "Woodblock",
	"Taiko Drum", "Melodic Tom", "Synth Drum", "Reverse Cymbal",
	"Guitar Fret Noise", "Breath Noise", "Seashore", "Bird Tweet",
	"Telephone Ring", "Helicopter", "Applause", "Gunshot",
]

var l10n: ClefL10n

var _tree: Tree

func _ready() -> void:
	title = l10n.t("Select Instrument") if l10n else "Select Instrument"
	min_size = Vector2(320, 420)
	size = Vector2(320, 420)
	get_ok_button().text = l10n.t("Cancel") if l10n else "Cancel"

	var vbox := VBoxContainer.new()
	add_child(vbox)

	_tree = Tree.new()
	_tree.size_flags_vertical = Control.SIZE_EXPAND_FILL
	_tree.hide_root = true
	_tree.columns = 1
	vbox.add_child(_tree)

	_tree.item_activated.connect(_on_item_activated)
	_tree.item_selected.connect(_on_item_selected)
	_tree.set_allow_reselect(true)


## 用 SF2 patches 填充弹窗（优先），patches 为空时 fallback GM
func populate(patches: Array) -> void:
	_tree.clear()
	var root := _tree.create_item()

	if patches.is_empty():
		_populate_gm_fallback(root)
		return

	# 按 gm_category 分组
	var categories: Dictionary = {}
	for p in patches:
		var cat: String
		if p is Dictionary:
			cat = p.get("gm_category", "Other")
		else:
			cat = p.gm_category
		if not categories.has(cat):
			categories[cat] = []
		categories[cat].append(p)

	for cat_name in categories:
		var cat_item := _tree.create_item(root)
		cat_item.set_text(0, cat_name)
		cat_item.set_collapsed(false)
		for p in categories[cat_name]:
			var item := _tree.create_item(cat_item)
			var preset: int
			var name: String
			if p is Dictionary:
				preset = p.get("preset_index", 0)
				name = p.get("name", "")
			else:
				preset = p.preset_index
				name = p.name
			item.set_text(0, "%d: %s" % [preset, name])
			item.set_metadata(0, preset)


func _populate_gm_fallback(root: TreeItem) -> void:
	var cat_names := [
		"Piano", "Chromatic Percussion", "Organ", "Guitar",
		"Bass", "Strings", "Ensemble", "Brass",
		"Reed", "Pipe", "Synth Lead", "Synth Pad",
		"Synth Effects", "Ethnic", "Percussive", "Sound Effects",
	]
	var root_item := _tree.create_item(root)
	root_item.set_text(0, "GM (SF2 未加载)")
	for ci in range(16):
		var cat_item := _tree.create_item(root_item)
		cat_item.set_text(0, cat_names[ci])
		cat_item.set_collapsed(true)
		for i in range(8):
			var preset: int = ci * 8 + i
			if preset >= GM_NAMES.size():
				break
			var item := _tree.create_item(cat_item)
			item.set_text(0, "%d: %s" % [preset, GM_NAMES[preset]])
			item.set_metadata(0, preset)


func _on_item_selected() -> void:
	var item := _tree.get_selected()
	if item and item.get_metadata(0) != null:
		var preset: int = item.get_metadata(0)
		instrument_selected.emit(preset)
		hide()


func _on_item_activated() -> void:
	_on_item_selected()
