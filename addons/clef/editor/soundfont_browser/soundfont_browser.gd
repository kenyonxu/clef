## 音色浏览器面板 — SF2 Patch 列表 + 搜索 + 试听 + 信息面板
@tool
class_name SoundfontBrowser
extends VBoxContainer

signal patch_selected(preset_index: int, patch: PatchData)

var _tree: Tree
var _search_line: LineEdit
var _info_panel: VBoxContainer
var _patches: Array[PatchData] = []
var _audition_player: Node = null
var _audition_bank: ClefBank = null
var _cleanup_timer: Timer = null
var _selected_item: TreeItem = null
var l10n: ClefL10n


func _ready() -> void:
	size_flags_vertical = Control.SIZE_EXPAND_FILL
	_build_ui()


func _build_ui() -> void:
	# Search bar
	var search_bar := HBoxContainer.new()
	search_bar.add_theme_constant_override("separation", 4)
	var search_label := Label.new()
	search_label.text = l10n.t("Search:") if l10n else "Search:"
	search_label.custom_minimum_size = Vector2i(36, 0)
	search_bar.add_child(search_label)
	_search_line = LineEdit.new()
	_search_line.placeholder_text = l10n.t("Name or number...") if l10n else "Name or number..."
	_search_line.text_changed.connect(_on_search_changed)
	_search_line.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	search_bar.add_child(_search_line)
	add_child(search_bar)

	# Patch list
	_tree = Tree.new()
	_tree.size_flags_vertical = Control.SIZE_EXPAND_FILL
	_tree.hide_root = true
	_tree.columns = 1
	_tree.set_column_title(0, l10n.t("Preset") if l10n else "Preset")
	_tree.item_activated.connect(_on_item_activated)
	_tree.item_selected.connect(_on_item_selected)
	add_child(_tree)

	# Info panel
	_info_panel = VBoxContainer.new()
	_info_panel.visible = false
	add_child(_info_panel)


func set_patches(patches: Array[PatchData]) -> void:
	_patches = patches
	_populate_tree(_search_line.text)


func clear_selection() -> void:
	if _selected_item:
		_selected_item.deselect(0)
		_selected_item = null
	_info_panel.visible = false


func _populate_tree(filter_text: String = "") -> void:
	_tree.clear()
	var root := _tree.create_item()
	var has_items := false

	for patch in _patches:
		if filter_text != "":
			var query := filter_text.to_lower()
			var name_match := patch.name.to_lower().find(query) >= 0
			var num_match := ("%03d" % patch.preset_index).find(query) >= 0
			if not name_match and not num_match:
				continue

		var item := _tree.create_item(root)
		item.set_text(0, "%03d %s" % [patch.preset_index, patch.name])
		item.set_metadata(0, patch)
		has_items = true

	if not has_items:
		_show_empty_state(l10n.t("No matching results") if l10n else "No matching results")


func _show_empty_state(text: String = "") -> void:
	if text == "":
		text = l10n.t("No soundfont loaded") if l10n else "No soundfont loaded"
	_tree.clear()
	var root := _tree.create_item()
	var item := _tree.create_item(root)
	item.set_text(0, text)
	item.set_custom_color(0, Color(0.5, 0.5, 0.5))
	item.set_selectable(0, false)


func _on_search_changed(text: String) -> void:
	_populate_tree(text)


func _on_item_activated() -> void:
	_try_audition()


func _on_item_selected() -> void:
	var item := _tree.get_selected()
	if item == null or item.get_metadata(0) == null:
		return
	var patch: PatchData = item.get_metadata(0)
	_update_info_panel(patch)


func _update_info_panel(patch: PatchData) -> void:
	_info_panel.visible = true
	for child in _info_panel.get_children():
		child.queue_free()

	var info_data := [
		[l10n.t("Range: %s") % patch.range_str if l10n else "Range: %s" % patch.range_str],
		[l10n.t("Velocity: %s") % patch.velocity_str if l10n else "Velocity: %s" % patch.velocity_str],
		[l10n.t("Sweet spot: %s") % patch.sweet_spot_str if l10n else "Sweet spot: %s" % patch.sweet_spot_str],
		[l10n.t("Quality: %s") % patch.quality_str if l10n else "Quality: %s" % patch.quality_str],
		[l10n.t("Layers: %d") % patch.layers if l10n else "Layers: %d" % patch.layers],
	]
	for label_text in info_data:
		var label := Label.new()
		label.text = label_text[0]
		_info_panel.add_child(label)

	# Highlight selected item
	if _selected_item:
		_selected_item.set_custom_color(0, Color.WHITE)
	_selected_item = _tree.get_selected()
	if _selected_item:
		_selected_item.set_custom_color(0, Color(0.7, 0.85, 1.0))


func _try_audition() -> void:
	var item := _tree.get_selected()
	if item == null or item.get_metadata(0) == null:
		return
	var patch: PatchData = item.get_metadata(0)
	if _audition_bank == null:
		return

	# Stop previous
	_stop_audition()

	_audition_player = AudioStreamPlayer.new()
	add_child(_audition_player)

	var voice := ClefVoice.new()
	voice.bank = _audition_bank
	voice.program = patch.preset_index
	voice.pitch_scale = patch.audition_note / 60.0  # Middle C = 60
	voice.volume_db = -6.0
	voice.ADSR.attack_time = 0.05
	voice.ADSR.sustain_level = 0.5
	voice.ADSR.release_time = 0.5

	_audition_player.stream = voice
	_audition_player.play()

	# Auto stop after 1.5s
	_cleanup_timer = Timer.new()
	_cleanup_timer.wait_time = 1.5
	_cleanup_timer.one_shot = true
	_cleanup_timer.timeout.connect(_stop_audition)
	add_child(_cleanup_timer)
	_cleanup_timer.start()


func _stop_audition() -> void:
	if _cleanup_timer and is_instance_valid(_cleanup_timer):
		_cleanup_timer.queue_free()
		_cleanup_timer = null
	if _audition_player and is_instance_valid(_audition_player):
		_audition_player.stop()
		_audition_player.queue_free()
		_audition_player = null


func set_bank(bank: ClefBank) -> void:
	_audition_bank = bank
	if bank == null:
		_show_empty_state()
	else:
		set_patches(bank.get_all_patches())
