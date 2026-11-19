# PAC-MAN and the Ghostly Adventures Patcher

Windows GUI for patching the Steam build of `PacMan.exe`
(SHA-256 `a279a2d634e7a34fc6f619ae185333d3bc3f6e8d3c6b94a69dd5258220232d9d`).

Options: frame rate (30/60/120/300/600), borderless window, v-sync (game default/on/off),
high-resolution crash fix, Hor+ for ultrawide, field-of-view scale, and resetting the saved
window `Left` position in the registry.

- `pacman_core.py`: patch logic (no GUI; validates the build and rebuilds every option from
  the original bytes on each apply).
- `pacman_patcher_gui.py`: tkinter front end. `--selftest` builds the window and exits.
- `asm/horplus2.asm`: source of the camera FOV routine placed in unused space in `.text`
  (assemble with `nasm -f bin`).

The Actions workflow builds `PacManPatcher.exe` with PyInstaller on every push to `main`;
download it from the run's Artifacts section.
