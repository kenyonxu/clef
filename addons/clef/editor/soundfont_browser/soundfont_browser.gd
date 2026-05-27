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
	# 搜索栏
	var search_bar := HBoxContainer.new()
	search_bar.add_theme_constant_override("separation", 4)
	var search_label := Label.new()
	search_label.text = l10n.t("Search:")
	search_label.custom_minimum_size = Vector2i(36, 0)
	search_bar.add_child(search_label)
	_search_line = LineEdit.new()
	_search_line.placeholder_text = l10n.t("Name or number...")
	_search_line.text_changed.connect(_on_search_changed)
	_search_line.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	search_bar.add_child(_search_line)
	add_child(search_bar)

	# Patch 列表
	_tree = Tree.new()
	_tree.size_flags_vertical = Control.SIZE_EXPAND_FILL
	_tree.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	_tree.hide_root = true
	_tree.columns = 1
	_tree.set_column_title(0, l10n.t("Preset"))
	_tree.item_selected.connect(_on_item_selected)
	_tree.item_activated.connect(_on_item_activated)
	add_child(_tree)

	# 信息面板
	var info_container := PanelContainer.new()
	info_container.custom_minimum_size = Vector2i(0, 80)
	var info_style := StyleBoxFlat.new()
	info_style.bg_color = Color(0.08, 0.08, 0.12)
	info_style.set_content_margin_all(6)
	info_container.add_theme_stylebox_override("panel", info_style)
	_info_panel = VBoxContainer.new()
	info_container.add_child(_info_panel)
	add_child(info_container)

	# 初始空状态
	_show_empty_state()


func load_profile(json_path: String) -> bool:
	var file := FileAccess.open(json_path, FileAccess.READ)
	if file == null:
		return false
	var json := JSON.new()
	var err := json.parse(file.get_as_text())
	file.close()
	if err != OK:
		return false
	var data = json.get_data()
	if not data is Dictionary or not data.has("presets"):
		return false
	_patches.clear()
	for key in data["presets"]:
		var preset_index := int(key)
		_patches.append(PatchData.from_dict(preset_index, data["presets"][key]))
	_patches.sort_custom(func(a, b): return a.preset_index < b.preset_index)
	_populate_tree("")
	return true


func get_patches() -> Array[PatchData]:
	return _patches


func _populate_tree(filter_text: String) -> void:
	_tree.clear()
	if _patches.is_empty():
		_show_empty_state()
		return

	var current_category: String = ""
	var category_root: TreeItem = null
	var has_items: bool = false

	for patch in _patches:
		var matches := true
		if filter_text != "":
			var query := filter_text.to_lower()
			matches = query in patch.name.to_lower() or query in str(patch.preset_index)
		if not matches:
			continue

		if patch.gm_category != current_category:
			current_category = patch.gm_category
			category_root = _tree.create_item()
			category_root.set_text(0, current_category)

		var item := _tree.create_item(category_root)
		item.set_text(0, "%03d %s" % [patch.preset_index, patch.name])
		item.set_metadata(0, patch)
		has_items = true

	if not has_items:
		_show_empty_state(l10n.t("No matching results"))


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


func _on_item_selected() -> void:
	var item := _tree.get_selected()
	if item == null or item.get_metadata(0) == null:
		_update_info_panel(null)
		return
	# 清除之前的高亮（使用主题默认字体色）
	if _selected_item != null and is_instance_valid(_selected_item):
		_selected_item.set_custom_color(0, _tree.get_theme_color("font_color", "Tree"))
	var patch: PatchData = item.get_metadata(0)
	item.set_custom_color(0, Color(1.0, 0.85, 0.4))
	_selected_item = item
	patch_selected.emit(patch.preset_index, patch)
	_update_info_panel(patch)


func _on_item_activated() -> void:
	var item := _tree.get_selected()
	if item == null or item.get_metadata(0) == null:
		return
	var patch: PatchData = item.get_metadata(0)
	_audition_patch(patch.preset_index)


func _update_info_panel(patch: PatchData) -> void:
	for child in _info_panel.get_children():
		child.queue_free()
	if patch == null:
		return
	var info := [
		l10n.t("Range: %s") % patch.format_range(patch.key_range),
		l10n.t("Velocity: %s") % patch.format_range(patch.vel_range),
		l10n.t("Sweet spot: %s") % patch.format_range(patch.sweet_spot),
		l10n.t("Quality: %s") % patch.quality,
		l10n.t("Layers: %d") % patch.vel_layers,
	]
	for text in info:
		var lbl := Label.new()
		lbl.text = text
		lbl.add_theme_color_override("font_color", Color(0.8, 0.8, 0.8))
		_info_panel.add_child(lbl)


func _gui_input(event: InputEvent) -> void:
	if event is InputEventKey and event.pressed and event.keycode == KEY_ENTER:
		_audition_selected()


func _audition_patch(preset_index: int) -> void:
	if _audition_bank == null:
		return
	var inst_infos: Array[ClefInstrumentInfo] = _audition_bank.get_instruments(preset_index, 60, 100, 0)
	if inst_infos.is_empty():
		return
	var voice := ClefVoice.new()
	_audition_player.add_child(voice)
	voice.start_note(inst_infos[0], 0, 60, 100, 1.0, inst_infos.size())
	voice.bus = "Master"
	# 1.5 秒后自动停止并清理
	_cleanup_timer = _cleanup_timer if _cleanup_timer != null else Timer.new()
	if not _cleanup_timer.is_inside_tree():
		add_child(_cleanup_timer)
	_cleanup_timer.stop()
	_cleanup_timer.wait_time = 1.5
	_cleanup_timer.one_shot = true
	_cleanup_timer.timeout.connect(func():
		if is_instance_valid(voice) and not voice.is_idle():
			voice.stop_note()
		)
	_cleanup_timer.start()


func _audition_selected() -> void:
	var item := _tree.get_selected()
	if item == null or item.get_metadata(0) == null:
		return
	var patch: PatchData = item.get_metadata(0)
	_audition_patch(patch.preset_index)


func setup_audition(sf2_path: String) -> bool:
	if sf2_path == "" or not FileAccess.file_exists(sf2_path):
		return false
	if _audition_player == null:
		_audition_player = Node.new()
		_audition_player.name = "AuditionPlayer"
		add_child(_audition_player)
	var result := Sf2Reader.read_file(sf2_path)
	if not result.ok:
		return false
	_audition_bank = ClefBank.new()
	_audition_bank.load_from_sf2(result.data)
	return true
