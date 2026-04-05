## PianoRoll 编辑操作辅助类
## 从 piano_roll.gd 提取的编辑逻辑：右键菜单、注解、力度、静音、音高偏移
class_name PianoRollActions
extends RefCounted

var _roll: PianoRoll


func _init(roll: PianoRoll) -> void:
	_roll = roll


# ─── 右键菜单 ───────────────────────────────────────────────

func create_context_menu() -> PopupMenu:
	_build_edit_menu()
	return _roll._context_menu


func _rebuild_context_menu() -> void:
	if _roll._context_menu != null:
		_roll._context_menu.queue_free()
		_roll._context_menu = null
	match _roll._mode:
		PianoRoll.Mode.EDITING:
			_build_edit_menu()
		PianoRoll.Mode.FEEDBACK:
			_build_feedback_menu()


func _build_edit_menu() -> void:
	var menu := PopupMenu.new()
	menu.id_pressed.connect(_handle_edit_menu_item)
	_roll._context_menu = menu
	_roll.add_child(menu)
	menu.add_item("删除音符", 0)
	menu.add_item("音高 +1", 1)
	menu.add_item("音高 -1", 2)
	menu.add_separator()
	menu.add_item("编辑力度...", 3)
	menu.add_separator()
	menu.add_item("屏蔽选中音符", 4)
	menu.add_item("反向屏蔽", 5)
	menu.add_separator()
	menu.add_item("导出修改后的 MIDI", 6)
	menu.add_item("导出修改后的 ABC", 7)


func _build_feedback_menu() -> void:
	var menu := PopupMenu.new()
	menu.id_pressed.connect(_handle_feedback_menu_item)
	_roll._context_menu = menu
	_roll.add_child(menu)
	menu.add_item("添加标注...", 10)
	menu.add_separator()
	menu.add_item("屏蔽选中音符", 11)
	menu.add_item("反向屏蔽", 12)
	menu.add_separator()
	menu.add_item("生成 Agent 反馈", 13)


func _handle_edit_menu_item(id: int) -> void:
	match id:
		0: _delete_selected()
		1: _shift_selected_pitch(1)
		2: _shift_selected_pitch(-1)
		3: _edit_velocity_popup()
		4: _toggle_mute_selected()
		5: _invert_mute_selected()
		6: _roll.export_requested.emit(_roll._notes)
		7: _roll.abc_export_requested.emit()


func _handle_feedback_menu_item(id: int) -> void:
	match id:
		10: _open_annotation_popup()
		11: _toggle_mute_selected()
		12: _invert_mute_selected()
		13: _roll.agent_feedback_requested.emit(get_agent_feedback())


# ─── 音符操作 ───────────────────────────────────────────────

func _delete_selected() -> void:
	var sel := _roll._selection
	if sel.is_empty():
		return
	var sorted := sel.duplicate()
	sorted.sort_custom(func(a, b): return a > b)
	var cmd := _roll.begin_command("delete", "删除 %d 个音符" % sorted.size())
	var deleted_items := []
	for idx in sorted:
		deleted_items.append({"index": idx, "note_data": _roll._clone_note(_roll._notes[idx])})
	cmd.before = {"deleted_items": deleted_items}
	for idx in sorted:
		_roll._notes.remove_at(idx)
	cmd.after = {"deleted_indices": sorted.duplicate()}
	sel.clear()
	_roll.commit_command(cmd)


func _toggle_mute_selected() -> void:
	var sel := _roll._selection
	if sel.is_empty():
		return
	var before_state := _roll._muted_indices.duplicate()
	var newly_muted := []
	var newly_unmuted := []
	for idx in sel:
		var found := _roll._muted_indices.find(idx)
		if found >= 0:
			_roll._muted_indices.remove_at(found)
			newly_unmuted.append(idx)
		else:
			_roll._muted_indices.append(idx)
			newly_muted.append(idx)
	if not newly_muted.is_empty() or not newly_unmuted.is_empty():
		var cmd := _roll.begin_command("mute", "屏蔽 %d / 恢复 %d" % [newly_muted.size(), newly_unmuted.size()])
		cmd.before = {"muted_indices": before_state}
		cmd.after = {"muted_indices": _roll._muted_indices.duplicate()}
		_roll.commit_command(cmd)
	_roll.queue_redraw()


func _invert_mute_selected() -> void:
	var sel := _roll._selection
	if sel.is_empty():
		return
	var before_state := _roll._muted_indices.duplicate()
	for idx in sel:
		var found := _roll._muted_indices.find(idx)
		if found >= 0:
			_roll._muted_indices.remove_at(found)
		else:
			_roll._muted_indices.append(idx)
	var cmd := _roll.begin_command("mute", "反向屏蔽 %d 个音符" % sel.size())
	cmd.before = {"muted_indices": before_state}
	cmd.after = {"muted_indices": _roll._muted_indices.duplicate()}
	_roll.commit_command(cmd)
	_roll.queue_redraw()


func _shift_selected_pitch(delta: int) -> void:
	var sel := _roll._selection
	if sel.is_empty():
		return
	var cmd := _roll.begin_command("property", "音高 %+d" % delta)
	var before_snap := []
	var after_snap := []
	for idx in sel:
		if idx >= 0 and idx < _roll._notes.size():
			before_snap.append({"index": idx, "pitch": _roll._notes[idx].pitch})
			_roll._notes[idx].pitch = clampi(_roll._notes[idx].pitch + delta, 0, 127)
			after_snap.append({"index": idx, "pitch": _roll._notes[idx].pitch})
	cmd.before = {"pitch_changes": before_snap}
	cmd.after = {"pitch_changes": after_snap}
	_roll.commit_command(cmd)


# ─── 力度编辑 ───────────────────────────────────────────────

func _edit_velocity_popup() -> void:
	var sel := _roll._selection
	if sel.is_empty():
		return
	var dialog := AcceptDialog.new()
	dialog.title = "编辑力度"
	var vbox := VBoxContainer.new()
	var label := Label.new()
	label.text = "力度 (0-127):"
	vbox.add_child(label)
	var input := LineEdit.new()
	input.placeholder_text = "100"
	if not sel.is_empty():
		var first_note := _roll._notes[sel[0]]
		input.text = str(first_note.velocity)
	input.alignment = HORIZONTAL_ALIGNMENT_CENTER
	vbox.add_child(input)
	dialog.add_child(vbox)
	dialog.confirmed.connect(func():
		var val := int(input.text)
		if val >= 0 and val <= 127:
			_set_selected_velocity(val)
		dialog.queue_free()
	)
	_roll.add_child(dialog)
	_roll._velocity_dialog = dialog
	dialog.popup_centered(Vector2i(200, 100))
	input.grab_focus()
	input.select_all()


func _set_selected_velocity(vel: int) -> void:
	var sel := _roll._selection
	var cmd := _roll.begin_command("property", "力度 → %d" % vel)
	var before_snap := []
	var after_snap := []
	for idx in sel:
		if idx >= 0 and idx < _roll._notes.size():
			before_snap.append({"index": idx, "velocity": _roll._notes[idx].velocity})
			_roll._notes[idx].velocity = vel
			after_snap.append({"index": idx, "velocity": vel})
	cmd.before = {"velocity_changes": before_snap}
	cmd.after = {"velocity_changes": after_snap}
	_roll.commit_command(cmd)


# ─── 标注 ───────────────────────────────────────────────────

func _open_annotation_popup() -> void:
	if _roll._selection.is_empty():
		return
	if _roll._annotation_popup == null:
		_create_annotation_popup()
	_roll._annotation_popup.position = _roll.get_global_mouse_position() + Vector2(5, 5)
	_roll._annotation_popup.visible = true


func _create_annotation_popup() -> void:
	var popup := PanelContainer.new()
	var vbox := VBoxContainer.new()
	var sev_hbox := HBoxContainer.new()
	var sev_label := Label.new()
	sev_label.text = "严重度:"
	sev_hbox.add_child(sev_label)
	var sev_option := OptionButton.new()
	sev_option.add_item("info")
	sev_option.add_item("warning")
	sev_option.add_item("error")
	sev_hbox.add_child(sev_option)
	vbox.add_child(sev_hbox)
	var text_label := Label.new()
	text_label.text = "备注:"
	vbox.add_child(text_label)
	var text_input := TextEdit.new()
	text_input.custom_minimum_size = Vector2(280, 60)
	vbox.add_child(text_input)
	var btn_hbox := HBoxContainer.new()
	btn_hbox.add_spacer(true)
	var cancel_btn := Button.new()
	cancel_btn.text = "取消"
	var confirm_btn := Button.new()
	confirm_btn.text = "确认"
	btn_hbox.add_child(cancel_btn)
	btn_hbox.add_child(confirm_btn)
	vbox.add_child(btn_hbox)
	popup.add_child(vbox)
	_roll.add_child(popup)
	_roll._annotation_popup = popup
	popup.visible = false
	cancel_btn.pressed.connect(func(): popup.visible = false)
	confirm_btn.pressed.connect(func():
		_add_annotation_from_popup(sev_option.selected, text_input.text.strip_edges())
		popup.visible = false
	)


func _add_annotation_from_popup(sev_index: int, text: String) -> void:
	if text.is_empty():
		return
	var severity: String = ["info", "warning", "error"][sev_index] if sev_index < 3 else "info"
	var before_anns := _roll._annotations.duplicate()
	for idx in _roll._selection:
		var ann := _roll._make_annotation(idx, text, severity)
		_roll._annotations.append(ann)
		_roll.annotation_added.emit(idx, text, severity)
	var cmd := _roll.begin_command("annotation", "添加标注: %s" % text)
	cmd.before = {"annotations": before_anns}
	cmd.after = {"annotations": _roll._annotations.duplicate()}
	_roll.commit_command(cmd)
	_roll.queue_redraw()


# ─── 注解绘制 ───────────────────────────────────────────────

func draw_annotations() -> void:
	var colors := {
		"info": Color(0.3, 0.7, 1.0),
		"warning": Color(1.0, 0.8, 0.2),
		"error": Color(1.0, 0.3, 0.3),
	}
	var drawn_count: Dictionary = {}
	for ann in _roll._annotations:
		if ann.note_index < 0 or ann.note_index >= _roll._notes.size():
			continue
		var note := _roll._notes[ann.note_index]
		var x: float = _roll._time_to_x(note.start_time)
		var y: float = _roll._pitch_to_y(note.pitch + 1)
		var offset: int = drawn_count.get(ann.note_index, 0)
		drawn_count[ann.note_index] = offset + 1
		var color: Color = colors.get(ann.severity, colors["info"])
		var tri_x: float = x + float(offset) * 8.0
		var tri_size := 6.0
		var points := PackedVector2Array([
			Vector2(tri_x, y - 2),
			Vector2(tri_x + tri_size, y - 2),
			Vector2(tri_x + tri_size / 2, y - tri_size - 2),
		])
		_roll.draw_colored_polygon(points, color)


# ─── Agent 反馈 ──────────────────────────────────────────────

func get_agent_feedback() -> Dictionary:
	var annotations_data := []
	for ann in _roll._annotations:
		if ann.note_index < 0 or ann.note_index >= _roll._notes.size():
			continue
		var note := _roll._notes[ann.note_index]
		annotations_data.append({
			"channel": note.channel,
			"pitch": note.pitch,
			"severity": ann.severity,
			"note": ann.text,
		})
	return {
		"version": 1,
		"annotations": annotations_data,
	}
