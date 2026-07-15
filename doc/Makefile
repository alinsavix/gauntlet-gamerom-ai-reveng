SOURCES = INDEX.md 01_hardware.md 02_os_rom.md 03_game_rom_structure.md \
          04_game_subsystems.md 05_data_reference.md 06_maze_catalog.md \
          07_function_index.md 08_known_issues.md

OUTPUT = gauntlet2_docs.pdf

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

check:
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
	python3 generated/generate_rom_byte_coverage.py --check
	python3 generated/generate_ram_linear_scan.py --check
	python3 check_confidence_labels.py
	python3 check_audit_completion.py

.PHONY: clean check
