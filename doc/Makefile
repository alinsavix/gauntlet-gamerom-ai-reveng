SOURCES = INDEX.md 01_hardware.md 02_os_rom.md 03_game_rom_structure.md \
          04_game_subsystems.md 05_data_reference.md 06_maze_catalog.md \
          07_function_index.md 08_known_issues.md

OUTPUT = gauntlet2_docs.pdf

# The checkers read these UTF-8 documents with Python's default encoding,
# which is cp1252 on Windows and makes them die on the first en dash.
export PYTHONUTF8 := 1

# The contract generators invoke "r2" through Python's subprocess, which on
# Windows goes to CreateProcess -- and CreateProcess only ever appends .exe,
# so the r2.bat that the radare2 Windows build ships is invisible to them.
# Copy radare2.exe aside as r2.exe and put that directory first on PATH.
# Non-Windows hosts already have a real r2 executable, so all of this is
# skipped and `check` gains no extra prerequisite.
R2_SHIM := $(CURDIR)/.r2shim
ifeq ($(OS),Windows_NT)
export PATH := $(R2_SHIM);$(PATH)
R2_SHIM_DEP := $(R2_SHIM)/r2.exe
endif

$(R2_SHIM)/r2.exe:
	@mkdir -p "$(R2_SHIM)"
	@src="$$(command -v radare2 2>/dev/null)"; \
	if [ -z "$$src" ]; then \
		bat="$$(command -v r2 2>/dev/null)"; \
		if [ -n "$$bat" ]; then src="$$(dirname "$$bat")/radare2.exe"; fi; \
	fi; \
	if [ ! -f "$$src" ]; then \
		echo "radare2 not found on PATH. Install it (or add its bin directory)" >&2; \
		echo "and re-run; the OS/game contract checks all shell out to it." >&2; \
		exit 1; \
	fi; \
	cp "$$src" "$@" && echo "r2.exe shim created in $(R2_SHIM) from $$src"

$(OUTPUT): $(SOURCES) pdf-header.tex Makefile
	pandoc $(SOURCES) \
		--pdf-engine=xelatex \
		--toc --toc-depth=2 \
		-V papersize=letter \
		-V geometry:margin=1in \
		-V colorlinks=true -V linkcolor=blue \
		-V fontsize=11pt \
		-H pdf-header.tex \
		--syntax-highlighting=tango \
		--lua-filter=table-widths.lua \
		-o $(OUTPUT)

clean:
	rm -f $(OUTPUT)
	rm -rf $(R2_SHIM)

check: $(R2_SHIM_DEP)
	python3 generated/generate_maze_catalog.py --check
	python3 generated/generate_rom_regions.py --check
	python3 generated/generate_r2_loader.py --check --run-check
	python3 generated/generate_os_entry_candidates.py --check
	python3 generated/generate_os_boot_contracts.py --check
	python3 generated/generate_os_memory_test_contracts.py --check
	python3 generated/generate_os_text_contracts.py --check
	python3 generated/generate_os_numeric_display_contracts.py --check
	python3 generated/generate_os_core_contracts.py --check
	python3 generated/generate_os_selftest_helper_contracts.py --check
	python3 generated/generate_os_selftest_screen_contracts.py --check
	python3 generated/generate_os_sound_contracts.py --check
	python3 generated/generate_os_coin_config_contracts.py --check
	python3 generated/generate_os_eeprom_contracts.py --check
	python3 generated/generate_os_operator_ui_contracts.py --check
	python3 generated/generate_os_callable_coverage.py --check
	python3 generated/generate_os_control_target_report.py --check
	python3 generated/generate_os_ram_operand_report.py --check
	python3 generated/generate_os_data_xrefs.py --check
	python3 generated/generate_os_residue_contracts.py --check
	python3 generated/generate_os_legacy_module_contracts.py --check
	python3 generated/generate_os_all_function_coverage.py --check
	python3 generated/generate_os_rom_coverage.py --check
	python3 generated/generate_main_loop_contracts.py --check --run-check
	python3 generated/generate_maze_contracts.py --check --run-check
	python3 generated/generate_player_collision_contracts.py --check --run-check
	python3 generated/generate_monster_combat_contracts.py --check --run-check
	python3 generated/generate_tport_forcefield_contracts.py --check --run-check
	python3 generated/generate_dragon_thief_exit_contracts.py --check --run-check
	python3 generated/generate_score_coin_dialog_contracts.py --check --run-check
	python3 generated/generate_startup_attract_contracts.py --check --run-check
	python3 generated/generate_player_lifecycle_contracts.py --check --run-check
	python3 generated/generate_player_runtime_contracts.py --check --run-check
	python3 generated/generate_mob_list_contracts.py --check --run-check
	python3 generated/generate_playfield_floor_contracts.py --check --run-check
	python3 generated/generate_wall_door_contracts.py --check --run-check
	python3 generated/generate_utility_init_contracts.py --check --run-check
	python3 generated/generate_movement_path_contracts.py --check --run-check
	python3 generated/generate_orchestration_sound_contracts.py --check --run-check
	python3 generated/generate_thief_secret_contracts.py --check --run-check
	python3 generated/generate_callable_coverage.py --check
	python3 generated/generate_control_target_report.py --check
	python3 generated/generate_ram_operand_report.py --check
	python3 generated/generate_data_flag_consumers.py --check
	python3 generated/generate_rom_byte_coverage.py --check
	python3 generated/generate_ram_linear_scan.py --check
	python3 check_confidence_labels.py
	python3 check_audit_completion.py

.PHONY: clean check
