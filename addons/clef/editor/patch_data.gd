## SF2 Patch 数据模型
class_name PatchData extends RefCounted

var preset_index: int
var name: String
var gm_category: String
var key_range: Vector2i  ## [lo, hi]
var vel_range: Vector2i  ## [lo, hi]
var sweet_spot: Vector2i  ## [lo, hi]
var vel_layers: int
var avg_attack: float
var avg_release: float
var quality: String
var characteristics: Array


static func from_dict(preset_index: int, data: Dictionary) -> PatchData:
	var pd := PatchData.new()
	pd.preset_index = preset_index
	pd.name = data.get("name", "")
	pd.gm_category = _preset_to_category(preset_index)
	var kr: Array = data.get("key_range", [0, 127])
	pd.key_range = Vector2i(int(kr[0]), int(kr[1]))
	var vr: Array = data.get("vel_range", [0, 127])
	pd.vel_range = Vector2i(int(vr[0]), int(vr[1]))
	var ss: Array = data.get("sweet_spot", [48, 84])
	pd.sweet_spot = Vector2i(int(ss[0]), int(ss[1]))
	pd.vel_layers = data.get("vel_layers", 0)
	pd.avg_attack = data.get("avg_attack", 0.0)
	pd.avg_release = data.get("avg_release", 0.0)
	pd.quality = data.get("quality", "")
	pd.characteristics = data.get("characteristics", [])
	return pd


## GM 标准分类 (每 8 个 preset 一组)
static func _preset_to_category(index: int) -> String:
	var categories := [
		"Piano", "Chromatic Percussion", "Organ", "Guitar",
		"Bass", "Strings", "Ensemble", "Brass",
		"Reed", "Pipe", "Synth Lead", "Synth Pad",
		"Synth Effects", "Ethnic", "Percussive", "Sound Effects",
	]
	return categories[mini(index / 8, categories.size() - 1)]


func format_range(range_v: Vector2i) -> String:
	return "%d-%d" % [range_v.x, range_v.y]
