@tool
extends EditorPlugin

var panel: VBoxContainer
var output: RichTextLabel
var status: Label
var worker: Thread
var log_path: String = "res://build/gba/editor.log"
var last_log: String = ""

func _enter_tree() -> void:
	panel = VBoxContainer.new()
	panel.name = "GBA Export"
	panel.custom_minimum_size = Vector2(0, 220)
	status = Label.new()
	status.text = "Build GBA: progetto salvato su disco → C/libtonc → make → ROM."
	panel.add_child(status)
	output = RichTextLabel.new()
	output.size_flags_vertical = Control.SIZE_EXPAND_FILL
	output.selection_enabled = true
	output.scroll_following = true
	panel.add_child(output)
	add_control_to_bottom_panel(panel, "GBA Export")
	add_tool_menu_item("Build GBA", build_gba)
	set_process(false)

func build_gba() -> void:
	make_bottom_panel_item_visible(panel)
	if worker != null:
		status.text = "Build già in corso."
		return
	DirAccess.make_dir_recursive_absolute("res://build/gba")
	var log_file: FileAccess = FileAccess.open(log_path, FileAccess.WRITE)
	if log_file == null:
		output.text = "ERRORE: impossibile scrivere build/gba/editor.log"
		push_error(output.text)
		return
	log_file.close()
	last_log = ""
	output.text = "Analisi delle versioni salvate su disco e compilazione in corso…"
	status.text = "Build GBA in corso; log: build/gba/editor.log"
	var python: String = OS.get_environment("GBA_PYTHON")
	if python.is_empty(): python = "python" if OS.get_name() == "Windows" else "python3"
	var args: PackedStringArray = ["-u", ProjectSettings.globalize_path("res://addons/gba_export/export_gba.py"), "--project", ProjectSettings.globalize_path("res://"), "--log", "build/gba/editor.log"]
	worker = Thread.new()
	var error: Error = worker.start(_execute.bind(python, args))
	if error != OK:
		worker = null
		output.text = "ERRORE: impossibile avviare il thread di build (%d)." % error
		return
	set_process(true)

func _execute(executable: String, arguments: PackedStringArray) -> Dictionary:
	var captured: Array = []
	var code: int = OS.execute(executable, arguments, captured, true, false)
	return {"code": code, "output": "\n".join(captured)}

func _process(_delta: float) -> void:
	if FileAccess.file_exists(log_path):
		var text: String = FileAccess.get_file_as_string(log_path)
		if text != last_log:
			last_log = text
			output.text = text
	if worker != null and not worker.is_alive():
		var result: Dictionary = worker.wait_to_finish()
		worker = null
		set_process(false)
		if FileAccess.file_exists(log_path):
			last_log = FileAccess.get_file_as_string(log_path)
			output.text = last_log
		if last_log.is_empty(): output.text = str(result["output"])
		status.text = "ROM generata: build/gba/game.gba" if int(result["code"]) == 0 else "Build GBA fallita: vedere errori con file e riga."
		if int(result["code"]) != 0:
			if output.text.is_empty(): output.text = "Python non disponibile. Impostare GBA_PYTHON oppure installare Python 3.11+."
			push_error(status.text)
		else: print(status.text)

func _exit_tree() -> void:
	remove_tool_menu_item("Build GBA")
	set_process(false)
	# OS.execute ha un timeout nel driver Python; nessun thread sopravvive al plugin.
	if worker != null:
		worker.wait_to_finish()
		worker = null
	remove_control_from_bottom_panel(panel)
	panel.queue_free()
