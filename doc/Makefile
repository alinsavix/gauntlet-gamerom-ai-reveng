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
	python3 generate_maze_catalog.py --check
	python3 generate_rom_regions.py --check
	python3 generate_r2_loader.py --check --run-check
	python3 generate_main_loop_contracts.py --check --run-check
	python3 generate_maze_contracts.py --check --run-check
	python3 generate_player_collision_contracts.py --check --run-check
	python3 generate_monster_combat_contracts.py --check --run-check
	python3 generate_tport_forcefield_contracts.py --check --run-check
	python3 generate_dragon_thief_exit_contracts.py --check --run-check
	python3 generate_score_coin_dialog_contracts.py --check --run-check
	python3 generate_startup_attract_contracts.py --check --run-check
	python3 generate_player_lifecycle_contracts.py --check --run-check
	python3 generate_player_runtime_contracts.py --check --run-check
	python3 generate_mob_list_contracts.py --check --run-check
	python3 generate_playfield_floor_contracts.py --check --run-check
	python3 generate_wall_door_contracts.py --check --run-check
	python3 generate_utility_init_contracts.py --check --run-check
	python3 generate_movement_path_contracts.py --check --run-check
	python3 generate_orchestration_sound_contracts.py --check --run-check
	python3 generate_thief_secret_contracts.py --check --run-check
	python3 generate_callable_coverage.py --check
	python3 generate_control_target_report.py --check
	python3 generate_ram_operand_report.py --check
	python3 generate_rom_byte_coverage.py --check
	python3 generate_ram_linear_scan.py --check
	python3 check_confidence_labels.py
	python3 check_audit_completion.py

.PHONY: clean check
