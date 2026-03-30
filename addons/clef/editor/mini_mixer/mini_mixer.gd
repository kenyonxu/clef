## 迷你混音台 — 16 通道音量滑块 + 颜色标识 + 静音 + 主音量
@tool
class_name MiniMixer
extends VBoxContainer

const ChannelColors = preload("res://addons/clef/editor/channel_colors.gd")

signal channel_volume_changed(channel: int, volume_db: float)
signal channel_mute_changed(channel: int, muted: bool)
signal master_volume_changed(volume_db: float)

const CHANNEL_COUNT: int = 16

## GM Level 1 乐器名 (128 presets)
const GM_INSTRUMENT_NAMES: PackedStringArray = [
	"Acoustic Grand Piano", "Bright Acoustic Piano", "Electric Grand Piano",
	"Honky-tonk Piano", "Electric Piano 1", "Electric Piano 2",
	"Harpsichord", "Clavinet", "Celesta", "Glockenspiel",
	"Music Box", "Vibraphone", "Marimba", "Xylophone",
	"Tubular Bells", "Dulcimer", "Drawbar Organ", "Percussive Organ",
	"Rock Organ", "Church Organ", "Reed Organ", "Accordion",
	"Harmonica", "Tango Accordion", "Acoustic Guitar(nylon)",
	"Acoustic Guitar(steel)", "Electric Guitar(jazz)", "Electric Guitar(clean)",
	"Electric Guitar(muted)", "Overdriven Guitar", "Distortion Guitar",
	"Guitar Harmonics", "Acoustic Bass", "Electric Bass(finger)",
	"Electric Bass(pick)", "Fretless Bass", "Slap Bass 1", "Slap Bass 2",
	"Synth Bass 1", "Synth Bass 2", "Violin", "Viola",
	"Cello", "Contrabass", "Tremolo Strings", "Pizzicato Strings",
	"Orchestral Harp", "Timpani", "String Ensemble 1", "String Ensemble 2",
	"Synth Strings 1", "Synth Strings 2", "Choir Aahs", "Voice Oohs",
	"Synth Choir", "Orchestra Hit", "Trumpet", "Trombone",
	"Tuba", "Muted Trumpet", "French Horn", "Brass Section",
	"Synth Brass 1", "Synth Brass 2", "Soprano Sax", "Alto Sax",
	"Tenor Sax", "Baritone Sax", "Oboe", "English Horn",
	"Bassoon", "Clarinet", "Piccolo", "Flute",
	"Recorder", "Pan Flute", "Blown Bottle", "Shakuhachi",
	"Whistle", "Ocarina", "Lead 1 (square)", "Lead 2 (sawtooth)",
	"Lead 3 (calliope)", "Lead 4 (chiff)", "Lead 5 (charang)",
	"Lead 6 (voice)", "Lead 7 (fifths)", "Lead 8 (bass+lead)",
	"Pad 1 (new age)", "Pad 2 (warm)", "Pad 3 (polysynth)",
	"Pad 4 (choir)", "Pad 5 (bowed)", "Pad 6 (metallic)",
	"Pad 7 (halo)", "Pad 8 (sweep)", "FX 1 (rain)", "FX 2 (soundtrack)",
	"FX 3 (crystal)", "FX 4 (atmosphere)", "FX 5 (brightness)",
	"FX 6 (goblins)", "FX 7 (echoes)", "FX 8 (sci-fi)",
	"Sitar", "Banjo", "Shamisen", "Koto", "Kalimba",
	"Bagpipe", "Fiddle", "Shanai", "Tinkle Bell", "Agogo",
	"Steel Drums", "Woodblock", "Taiko Drum", "Melodic Tom",
	"Synth Drum", "Reverse Cymbal", "Guitar Fret Noise",
	"Breath Noise", "Seashore", "Bird Tweet", "Telephone Ring",
	"Helicopter", "Applause", "Gunshot",
]

var _channel_sliders: Array[VSlider] = []
var _mute_buttons: Array[Button] = []
var _channel_labels: Array[Label] = []
var _color_indicators: Array[ColorRect] = []
var _master_slider: HSlider
var _master_label: Label


func _ready() -> void:
	size_flags_horizontal = Control.SIZE_EXPAND_FILL
	size_flags_vertical = Control.SIZE_EXPAND_FILL
	_build_ui()


func _channel_panel_style() -> StyleBoxFlat:
	var style := StyleBoxFlat.new()
	style.bg_color = Color(0.12, 0.12, 0.14)
	style.set_border_width_all(1)
	style.set_border_color(Color(0.25, 0.25, 0.28))
	style.set_content_margin_all(4)
	style.set_corner_radius_all(2)
	return style


func _build_ui() -> void:
	var channels_row := HBoxContainer.new()
	channels_row.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	channels_row.size_flags_vertical = Control.SIZE_EXPAND_FILL
	channels_row.add_theme_constant_override("separation", 3)

	for i in range(CHANNEL_COUNT):
		var panel := PanelContainer.new()
		panel.size_flags_horizontal = Control.SIZE_EXPAND_FILL
		panel.size_flags_vertical = Control.SIZE_EXPAND_FILL
		panel.add_theme_stylebox_override("panel", _channel_panel_style())

		var strip := VBoxContainer.new()
		strip.size_flags_horizontal = Control.SIZE_EXPAND_FILL
		strip.size_flags_vertical = Control.SIZE_EXPAND_FILL
		strip.add_theme_constant_override("separation", 2)

		# 通道颜色指示条（有乐器时才显示）
		var color_rect := ColorRect.new()
		color_rect.color = ChannelColors.COLORS[i]
		color_rect.custom_minimum_size = Vector2i(0, 6)
		color_rect.visible = false
		strip.add_child(color_rect)
		_color_indicators.append(color_rect)

		var ch_lbl := Label.new()
		ch_lbl.text = "Ch%d" % i
		ch_lbl.horizontal_alignment = HORIZONTAL_ALIGNMENT_CENTER
		ch_lbl.add_theme_font_size_override("font_size", 18)
		ch_lbl.add_theme_color_override("font_color", Color(0.7, 0.7, 0.7))
		ch_lbl.tooltip_text = "Channel %d" % i
		strip.add_child(ch_lbl)
		_channel_labels.append(ch_lbl)

		var slider := VSlider.new()
		slider.min_value = 0.0
		slider.max_value = 1.0
		slider.step = 0.01
		slider.value = 1.0
		slider.size_flags_vertical = Control.SIZE_EXPAND_FILL
		slider.size_flags_horizontal = Control.SIZE_EXPAND_FILL
		slider.custom_minimum_size = Vector2i(20, 80)
		slider.tooltip_text = "Channel %d volume" % i
		slider.drag_ended.connect(_on_channel_slider_ended.bind(i))
		strip.add_child(slider)
		_channel_sliders.append(slider)

		var mute_btn := Button.new()
		mute_btn.text = "M"
		mute_btn.custom_minimum_size = Vector2i(0, 28)
		mute_btn.toggle_mode = true
		mute_btn.add_theme_font_size_override("font_size", 18)
		mute_btn.tooltip_text = "Mute Channel %d" % i
		_set_mute_style(mute_btn, false)
		mute_btn.toggled.connect(_on_mute_toggled.bind(i, mute_btn))
		strip.add_child(mute_btn)
		_mute_buttons.append(mute_btn)

		panel.add_child(strip)
		channels_row.add_child(panel)

	add_child(channels_row)

	# 主音量行
	var master_row := HBoxContainer.new()
	master_row.add_theme_constant_override("separation", 8)

	var master_title := Label.new()
	master_title.text = "Master"
	master_title.custom_minimum_size = Vector2i(60, 0)
	master_title.add_theme_font_size_override("font_size", 18)
	master_title.add_theme_color_override("font_color", Color(0.9, 0.9, 0.7))
	master_row.add_child(master_title)

	_master_slider = HSlider.new()
	_master_slider.min_value = -60.0
	_master_slider.max_value = 6.0
	_master_slider.step = 1.0
	_master_slider.value = -12.0
	_master_slider.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	_master_slider.tooltip_text = "Master volume"
	_master_slider.value_changed.connect(_on_master_slider_changed)
	master_row.add_child(_master_slider)

	_master_label = Label.new()
	_master_label.text = "-12 dB"
	_master_label.custom_minimum_size = Vector2i(64, 0)
	_master_label.add_theme_font_size_override("font_size", 18)
	_master_label.add_theme_color_override("font_color", Color(0.7, 0.7, 0.7))
	master_row.add_child(_master_label)

	add_child(master_row)


## 清除所有通道的乐器指示（加载新文件前调用）
func clear_instruments() -> void:
	for i in range(_color_indicators.size()):
		_color_indicators[i].visible = false
		_channel_labels[i].tooltip_text = "Channel %d" % i


## 更新通道乐器名（由 Bridge.midi_program_change 触发，更新 tooltip + 颜色指示条）
func set_channel_instrument(channel: int, preset_index: int) -> void:
	if channel < 0 or channel >= _channel_labels.size():
		return
	var name: String = ""
	if preset_index >= 0 and preset_index < GM_INSTRUMENT_NAMES.size():
		name = GM_INSTRUMENT_NAMES[preset_index]
	var lbl: Label = _channel_labels[channel]
	lbl.tooltip_text = "Ch%d: %s" % [channel, name]
	_color_indicators[channel].visible = name != ""


func _set_mute_style(btn: Button, muted: bool) -> void:
	var style := StyleBoxFlat.new()
	if muted:
		style.bg_color = Color(0.35, 0.15, 0.15)
		btn.add_theme_color_override("font_color", Color(1.0, 0.4, 0.4))
	else:
		style.bg_color = Color(0.18, 0.18, 0.20)
		btn.add_theme_color_override("font_color", Color(0.7, 0.7, 0.7))
	style.set_content_margin_all(4)
	style.set_corner_radius_all(2)
	btn.add_theme_stylebox_override("normal", style)


func _on_channel_slider_ended(value_changed: bool, channel: int) -> void:
	channel_volume_changed.emit(channel, _channel_sliders[channel].value)


func _on_master_slider_changed(value: float) -> void:
	_master_label.text = "%.0f dB" % value
	master_volume_changed.emit(value)


func _on_mute_toggled(pressed: bool, channel: int, btn: Button) -> void:
	_set_mute_style(btn, pressed)
	_channel_sliders[channel].editable = not pressed
	channel_mute_changed.emit(channel, pressed)
