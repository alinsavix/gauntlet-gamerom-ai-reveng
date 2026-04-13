SOURCES = INDEX.md 01_hardware.md 02_os_rom.md 03_game_rom_structure.md \
          04_game_subsystems.md 05_data_reference.md 06_maze_catalog.md \
          07_function_index.md 08_known_issues.md

OUTPUT = gauntlet2_docs.pdf

$(OUTPUT): $(SOURCES) pdf-header.tex
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

.PHONY: clean
