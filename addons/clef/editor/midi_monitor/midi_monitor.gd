## MIDI 监视器面板 — 实时事件流 + 过滤 + 统计
@tool
class_name MidiMonitor
extends VBoxContainer

## 事件类型
enum EventType {
	NOTE_ON,
	NOTE_OFF,
	CC,
	PITCH_BEND,
	PROGRAM_CHANGE,
}

## 事件数据
class MidiEvent:
	var type: int
	var channel: int
	var data1: int
	var data2: int
	var timestamp: float

	func _init(t: int, ch: int, d1: int, d2: int = 0) -> void:
		type = t
		channel = ch
		data1 = d1
		data2 = d2
		timestamp = Time.get_ticks_msec() / 1000.0


## 事件颜色（按类型）
const _EVENT_COLORS: Dictionary = {
	EventType.NOTE_ON: Color(0.4, 1.0, 0.4),
	EventType.NOTE_OFF: Color(0.6, 0.6, 0.6),
	EventType.CC: Color(0.4, 0.7, 1.0),
	EventType.PITCH_BEND: Color(1.0, 0.7, 0.3),
	EventType.PROGRAM_CHANGE: Color(0.9, 0.5, 0.9),
}

const _EVENT_NAMES: Dictionary = {
	EventType.NOTE_ON: "NoteOn",
	EventType.NOTE_OFF: "NoteOff",
	EventType.CC: "CC",
	EventType.PITCH_BEND: "PB",
	EventType.PROGRAM_CHANGE: "PC",
}

const MAX_EVENTS: int = 500

var _event_log: RichTextLabel
var _stats_label: Label
var _events: Array[MidiEvent] = []
var _active_notes: int = 0
var _event_count: int = 0
var _filter_channel: int = -1
var _filter_types: int = 0x1F
var _auto_scroll: bool = true
var _rate_timer: Timer = null
var _rate_count: int = 0
var _current_rate: int = 0


func _ready() -> void:
	size_flags_vertical = Control.SIZE_EXPAND_FILL
	size_flags_horizontal = Control.SIZE_EXPAND_FILL
	_build_ui()


func _build_ui() -> void:
	# 过滤工具栏
	var toolbar := HBoxContainer.new()
	toolbar.add_theme_constant_override("separation", 4)
	toolbar.custom_minimum_size = Vector2i(0, 28)

	var ch_label := Label.new()
	ch_label.text = "Ch:"
	toolbar.add_child(ch_label)

	var ch_btn := Button.new()
	ch_btn.text = "All"
	ch_btn.custom_minimum_size = Vector2i(36, 0)
	ch_btn.toggle_mode = true
	ch_btn.button_pressed = true
	ch_btn.tooltip_text = "Channel filter: All"
	toolbar.add_child(ch_btn)

	for type_key in [EventType.NOTE_ON, EventType.CC, EventType.PITCH_BEND, EventType.PROGRAM_CHANGE]:
		var btn := Button.new()
		btn.text = _EVENT_NAMES[type_key]
		btn.custom_minimum_size = Vector2i(42, 0)
		btn.toggle_mode = true
		btn.button_pressed = true
		btn.tooltip_text = "Toggle %s filter" % _EVENT_NAMES[type_key]
		btn.pressed.connect(_on_type_filter_pressed.bind(type_key, btn))
		toolbar.add_child(btn)

	var scroll_btn := Button.new()
	scroll_btn.text = "Auto"
	scroll_btn.custom_minimum_size = Vector2i(36, 0)
	scroll_btn.toggle_mode = true
	scroll_btn.button_pressed = true
	scroll_btn.tooltip_text = "Toggle auto-scroll"
	scroll_btn.pressed.connect(func(pressed: bool): _auto_scroll = pressed)
	toolbar.add_child(scroll_btn)

	var clear_btn := Button.new()
	clear_btn.text = "Clear"
	clear_btn.custom_minimum_size = Vector2i(36, 0)
	clear_btn.tooltip_text = "Clear event log"
	clear_btn.pressed.connect(_clear_log)
	toolbar.add_child(clear_btn)

	add_child(toolbar)

	# 事件流
	_event_log = RichTextLabel.new()
	_event_log.size_flags_vertical = Control.SIZE_EXPAND_FILL
	_event_log.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	_event_log.scroll_following = true
	_event_log.bbcode_enabled = true
	_event_log.fit_content = true
	add_child(_event_log)

	# 统计栏
	var stats_container := PanelContainer.new()
	stats_container.custom_minimum_size = Vector2i(0, 22)
	var stats_style := StyleBoxFlat.new()
	stats_style.bg_color = Color(0.08, 0.08, 0.12)
	stats_style.set_content_margin_all(4)
	stats_container.add_theme_stylebox_override("panel", stats_style)
	_stats_label = Label.new()
	_stats_label.add_theme_color_override("font_color", Color(0.7, 0.7, 0.7))
	stats_container.add_child(_stats_label)
	add_child(stats_container)

	# 事件率定时器（每秒统计）
	_rate_timer = Timer.new()
	_rate_timer.wait_time = 1.0
	_rate_timer.timeout.connect(_update_rate)
	add_child(_rate_timer)
	_rate_timer.start()


func connect_bridge(bridge: RefCounted) -> void:
	if bridge == null:
		return
	if "midi_note_on" in bridge:
		bridge.midi_note_on.connect(_on_midi_note_on)
	if "midi_note_off" in bridge:
		bridge.midi_note_off.connect(_on_midi_note_off)
	if "midi_cc" in bridge:
		bridge.midi_cc.connect(_on_midi_cc)
	if "midi_pitch_bend" in bridge:
		bridge.midi_pitch_bend.connect(_on_midi_pitch_bend)
	if "midi_program_change" in bridge:
		bridge.midi_program_change.connect(_on_midi_program_change)
	if "player_changed" in bridge:
		bridge.player_changed.connect(func(player):
			if player == null:
				_active_notes = 0
		)


# ─── 事件接收 ──────────────────────────────────────────

func _on_midi_note_on(ch: int, pitch: int, vel: int) -> void:
	_append_event(MidiEvent.new(EventType.NOTE_ON, ch, pitch, vel))
	_active_notes += 1
	_rate_count += 1


func _on_midi_note_off(ch: int, pitch: int) -> void:
	_append_event(MidiEvent.new(EventType.NOTE_OFF, ch, pitch, 0))
	_active_notes = maxi(0, _active_notes - 1)
	_rate_count += 1


func _on_midi_cc(ch: int, controller: int, value: int) -> void:
	_append_event(MidiEvent.new(EventType.CC, ch, controller, value))
	_rate_count += 1


func _on_midi_pitch_bend(ch: int, value: int) -> void:
	_append_event(MidiEvent.new(EventType.PITCH_BEND, ch, value, 0))
	_rate_count += 1


func _on_midi_program_change(ch: int, preset: int) -> void:
	_append_event(MidiEvent.new(EventType.PROGRAM_CHANGE, ch, preset, 0))
	_rate_count += 1


# ─── 事件渲染 ──────────────────────────────────────────

func _append_event(evt: MidiEvent) -> void:
	_events.append(evt)
	_event_count += 1
	if _events.size() > MAX_EVENTS:
		_events.pop_front()
		_event_log.clear()
		_rebuild_log()
		return
	_append_event_line(evt)


func _append_event_line(evt: MidiEvent) -> void:
	if not _passes_filter(evt):
		return
	var color: Color = _EVENT_COLORS.get(evt.type, Color(1, 1, 1))
	var text := _format_event(evt)
	_event_log.append_text("[color #%s]%s[/color]\n" % [color.to_html(false), text])
	if _auto_scroll:
		_event_log.scroll_to_line(_event_log.get_line_count() - 1)


func _format_event(evt: MidiEvent) -> String:
	match evt.type:
		EventType.NOTE_ON:
			return "Ch%-2d NoteOn  %-3d vel:%-3d" % [evt.channel, evt.data1, evt.data2]
		EventType.NOTE_OFF:
			return "Ch%-2d NoteOff %-3d" % [evt.channel, evt.data1]
		EventType.CC:
			return "Ch%-2d CC#%-3d val:%-3d" % [evt.channel, evt.data1, evt.data2]
		EventType.PITCH_BEND:
			return "Ch%-2d PitchBend %-5d" % [evt.channel, evt.data1]
		EventType.PROGRAM_CHANGE:
			return "Ch%-2d PC      %-3d" % [evt.channel, evt.data1]
		_:
			return "Ch%-2d ????" % evt.channel


func _rebuild_log() -> void:
	for evt in _events:
		_append_event_line(evt)


# ─── 过滤 ──────────────────────────────────────────────

func _passes_filter(evt: MidiEvent) -> bool:
	if _filter_channel >= 0 and evt.channel != _filter_channel:
		return false
	if not (_filter_types & (1 << evt.type)):
		return false
	return true


func _on_type_filter_pressed(type_val: int, btn: Button) -> void:
	if btn.button_pressed:
		_filter_types |= (1 << type_val)
	else:
		_filter_types &= ~(1 << type_val)
	_event_log.clear()
	_rebuild_log()


# ─── 统计 ──────────────────────────────────────────────

func _update_rate() -> void:
	_current_rate = _rate_count
	_rate_count = 0
	_stats_label.text = "Events: %d | Notes: %d | %d/s" % [_event_count, _active_notes, _current_rate]


func _clear_log() -> void:
	_events.clear()
	_active_notes = 0
	_event_count = 0
	_rate_count = 0
	_current_rate = 0
	_event_log.clear()
	_update_rate()
