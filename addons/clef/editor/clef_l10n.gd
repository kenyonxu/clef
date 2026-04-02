## Localization helper for the Clef editor plugin.
## Wraps a custom TranslationDomain so all plugin scripts can call ClefL10n.t().
@tool
class_name ClefL10n
extends RefCounted

const DOMAIN_NAME: StringName = &"clef"

var _domain: TranslationDomain


func _init() -> void:
	_domain = TranslationServer.get_or_add_domain(DOMAIN_NAME)
	_domain.set_locale_override(TranslationServer.get_tool_locale())


func setup() -> void:
	"""Scan locales/ directory and load all .translation files."""
	var dir := DirAccess.open("res://addons/clef/locales/")
	if dir == null:
		return
	dir.list_dir_begin()
	var file_name := dir.get_next()
	while file_name != "":
		if file_name.ends_with(".translation"):
			var translation = load("res://addons/clef/locales/" + file_name)
			if translation is Translation:
				_domain.add_translation(translation)
		file_name = dir.get_next()
	dir.list_dir_end()


func cleanup() -> void:
	if _domain:
		_domain.clear()
		if TranslationServer.has_domain(DOMAIN_NAME):
			TranslationServer.remove_domain(DOMAIN_NAME)
		_domain = null


func t(message: String, context: String = "") -> String:
	"""Translate a message using the clef domain. Falls back to message itself."""
	if _domain:
		return _domain.translate(message, context)
	return message


func refresh_locale() -> void:
	"""Re-sync with editor locale (call on locale change)."""
	if _domain:
		_domain.set_locale_override(TranslationServer.get_tool_locale())
