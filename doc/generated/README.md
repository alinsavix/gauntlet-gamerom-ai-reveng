# Generated audit artifacts

This directory contains the project's checked-in CSV catalogs and the Python
generators that create or verify them. It also contains `soundcmds.csv`, a
supplied reference table consumed by the documentation rather than generated
from the ROM images.

Run the complete regeneration and binary-evidence check from `doc/`:

```sh
make check
```

Individual generators can also be run from the repository root, for example:

```sh
python3 doc/generated/generate_maze_catalog.py --check
```

`generate_r2_loader.py` lives here with the other audit generators, but keeps
its generated `gauntlet_loader.r2` output one directory up in `doc/`.
