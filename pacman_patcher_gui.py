"""
PAC-MAN and the Ghostly Adventures Patcher - GUI.

Finds PacMan.exe (current folder, the tool's folder, or any Steam library), shows which
patches are applied, and lets you switch them. Run with --selftest to build the window
and exit (used by the automated build).
"""
import os
import re
import sys
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

import pacman_core as core

try:
    import winreg
except ImportError:  # not Windows
    winreg = None

APP_TITLE = "PAC-MAN and the Ghostly Adventures Patcher"
GAME_DIR = "Pac-Man and the Ghostly Adventures"
REG_PATH = r"Software\Monkey Bar Games\PacMan\Settings"


# ----------------------------------------------------------------------------- locating

def _steam_libraries():
    roots = []
    if winreg is not None:
        for hive, key, value in ((winreg.HKEY_CURRENT_USER, r"Software\Valve\Steam", "SteamPath"),
                                 (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\WOW6432Node\Valve\Steam", "InstallPath")):
            try:
                with winreg.OpenKey(hive, key) as k:
                    roots.append(os.path.normpath(winreg.QueryValueEx(k, value)[0]))
            except OSError:
                pass
    libs = []
    for root in roots:
        libs.append(root)
        vdf = os.path.join(root, "steamapps", "libraryfolders.vdf")
        try:
            with open(vdf, encoding="utf-8", errors="replace") as f:
                for m in re.finditer(r'"path"\s+"([^"]+)"', f.read()):
                    libs.append(os.path.normpath(m.group(1).replace("\\\\", "\\")))
        except OSError:
            pass
    seen, out = set(), []
    for lib in libs:
        if lib.lower() not in seen:
            seen.add(lib.lower())
            out.append(lib)
    return out


def find_game_exe():
    here = os.path.dirname(os.path.abspath(sys.executable if getattr(sys, "frozen", False) else __file__))
    candidates = [os.getcwd(), here]
    candidates += [os.path.join(lib, "steamapps", "common", GAME_DIR) for lib in _steam_libraries()]
    for d in candidates:
        p = os.path.join(d, "PacMan.exe")
        if os.path.isfile(p):
            return p
    return ""


# ----------------------------------------------------------------------------- registry

def read_window_settings():
    if winreg is None:
        return None
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, REG_PATH) as k:
            out = {}
            for name in ("Width", "Height", "Left", "Top", "Fullscreen"):
                try:
                    v = winreg.QueryValueEx(k, name)[0]
                    out[name] = v - (1 << 32) if isinstance(v, int) and v >= 1 << 31 else v
                except OSError:
                    pass
            return out
    except OSError:
        return None


def reset_window_left():
    # Same as: reg add "HKCU\Software\Monkey Bar Games\PacMan\Settings" /v Left /t REG_DWORD /d 0 /f
    with winreg.CreateKeyEx(winreg.HKEY_CURRENT_USER, REG_PATH, 0, winreg.KEY_SET_VALUE) as k:
        winreg.SetValueEx(k, "Left", 0, winreg.REG_DWORD, 0)


# ----------------------------------------------------------------------------- window

class App(ttk.Frame):
    def __init__(self, master):
        super().__init__(master, padding=12)
        self.master = master
        self.path_var = tk.StringVar()
        self.status_var = tk.StringVar()
        self.fps_var = tk.IntVar(value=30)
        self.borderless_var = tk.BooleanVar()
        self.vsync_var = tk.StringVar(value="default")
        self.hires_var = tk.BooleanVar()
        self.horplus_var = tk.BooleanVar()
        self.fov_var = tk.DoubleVar(value=100.0)
        self.fov_label_var = tk.StringVar()
        self.reg_var = tk.StringVar()
        self.loaded = False
        self._build()
        self.grid(sticky="nsew")

    # -- layout
    def _build(self):
        pad = {"padx": 6, "pady": 3}

        f = ttk.LabelFrame(self, text="Game executable", padding=8)
        f.grid(row=0, column=0, columnspan=2, sticky="ew", **pad)
        ttk.Entry(f, textvariable=self.path_var, width=70).grid(row=0, column=0, sticky="ew")
        ttk.Button(f, text="Browse...", command=self.browse).grid(row=0, column=1, padx=(6, 0))
        ttk.Label(f, textvariable=self.status_var, wraplength=560).grid(row=1, column=0, columnspan=2, sticky="w", pady=(6, 0))
        f.columnconfigure(0, weight=1)

        f = ttk.LabelFrame(self, text="1. Frame rate", padding=8)
        f.grid(row=1, column=0, sticky="nsew", **pad)
        for i, fps in enumerate(core.FPS_CHOICES):
            ttk.Radiobutton(f, text="%d FPS%s" % (fps, " (original)" if fps == 30 else ""),
                            variable=self.fps_var, value=fps).grid(row=i, column=0, sticky="w")

        f = ttk.LabelFrame(self, text="3. V-sync", padding=8)
        f.grid(row=1, column=1, sticky="nsew", **pad)
        for i, (val, text) in enumerate((("default", "Game default (on in fullscreen only)"),
                                         ("on", "Always on (caps FPS at refresh rate)"),
                                         ("off", "Always off"))):
            ttk.Radiobutton(f, text=text, variable=self.vsync_var, value=val).grid(row=i, column=0, sticky="w")

        f = ttk.LabelFrame(self, text="Display", padding=8)
        f.grid(row=2, column=0, columnspan=2, sticky="ew", **pad)
        ttk.Checkbutton(f, text="2. Borderless window (when Fullscreen is off)",
                        variable=self.borderless_var).grid(row=0, column=0, sticky="w")
        ttk.Checkbutton(f, text="4. High-resolution crash fix (above 2560x1440)",
                        variable=self.hires_var).grid(row=1, column=0, sticky="w")
        ttk.Checkbutton(f, text="Hor+ for ultrawide (widen the view instead of cropping it)",
                        variable=self.horplus_var).grid(row=2, column=0, sticky="w")

        f = ttk.LabelFrame(self, text="5. Field of view", padding=8)
        f.grid(row=3, column=0, columnspan=2, sticky="ew", **pad)
        ttk.Scale(f, from_=core.FOV_MIN * 100, to=core.FOV_MAX * 100, variable=self.fov_var,
                  command=self._fov_moved, length=360).grid(row=0, column=0, sticky="ew")
        ttk.Label(f, textvariable=self.fov_label_var, width=24).grid(row=0, column=1, padx=8)
        ttk.Button(f, text="Default", command=lambda: self._set_fov(100)).grid(row=0, column=2)
        ttk.Label(f, text="Scales the gameplay camera's view (applies to cameras that use the screen's "
                          "aspect ratio). Above 100% shows more of the scene.",
                  wraplength=560, foreground="#555").grid(row=1, column=0, columnspan=3, sticky="w", pady=(4, 0))
        f.columnconfigure(0, weight=1)

        b = ttk.Frame(self)
        b.grid(row=4, column=0, columnspan=2, sticky="ew", pady=(8, 4))
        self.apply_btn = ttk.Button(b, text="Apply patches", command=self.apply)
        self.apply_btn.pack(side="left", padx=6)
        self.restore_btn = ttk.Button(b, text="Restore original exe", command=self.restore)
        self.restore_btn.pack(side="left", padx=6)

        f = ttk.LabelFrame(self, text="6. Window position (registry)", padding=8)
        f.grid(row=5, column=0, columnspan=2, sticky="ew", **pad)
        ttk.Label(f, textvariable=self.reg_var).grid(row=0, column=0, sticky="w")
        self.reg_btn = ttk.Button(f, text="Reset Left to 0", command=self.reset_left)
        self.reg_btn.grid(row=0, column=1, padx=(12, 0))
        f.columnconfigure(0, weight=1)

        self._set_fov(100)
        self._set_enabled(False)

    # -- helpers
    def _set_fov(self, pct):
        self.fov_var.set(pct)
        self._fov_moved(pct)

    def _fov_moved(self, value):
        pct = int(round(float(value) / 5.0) * 5)
        if abs(self.fov_var.get() - pct) > 1e-6:
            self.fov_var.set(pct)
        self.fov_label_var.set("%d%%%s" % (pct, " (game default)" if pct == 100 else ""))

    def _set_enabled(self, on):
        for w in (self.apply_btn, self.restore_btn):
            w.state(["!disabled"] if on else ["disabled"])

    def _collect_options(self):
        return core.Options(fps=self.fps_var.get(), borderless=self.borderless_var.get(),
                            vsync=self.vsync_var.get(), hires_fix=self.hires_var.get(),
                            hor_plus=self.horplus_var.get(), fov_scale=round(self.fov_var.get()) / 100.0)

    def _show_options(self, o):
        self.fps_var.set(o.fps)
        self.borderless_var.set(o.borderless)
        self.vsync_var.set(o.vsync)
        self.hires_var.set(o.hires_fix)
        self.horplus_var.set(o.hor_plus)
        self._set_fov(int(round(o.fov_scale * 100)))

    # -- actions
    def refresh_registry(self):
        s = read_window_settings()
        if s is None:
            self.reg_var.set("No saved window settings found (the game creates them on first run).")
            self.reg_btn.state(["!disabled"] if winreg is not None else ["disabled"])
            return
        self.reg_var.set("Saved size %sx%s at Left=%s, Top=%s, Fullscreen=%s"
                         % (s.get("Width", "?"), s.get("Height", "?"), s.get("Left", "?"),
                            s.get("Top", "?"), s.get("Fullscreen", "?")))

    def load(self, path):
        self.path_var.set(path)
        self.loaded = False
        self._set_enabled(False)
        if not path:
            self.status_var.set("PacMan.exe was not found automatically. Use Browse to select it.")
            return
        try:
            data, base, opts = core.load(path)
        except core.UnsupportedBuild as e:
            self.status_var.set(str(e))
            return
        except OSError as e:
            self.status_var.set("Could not read the file: %s" % e)
            return
        self._show_options(opts)
        self.loaded = True
        self._set_enabled(True)
        self.status_var.set("Supported build. Current state: %s." % ("patched" if data != base else "original"))

    def browse(self):
        p = filedialog.askopenfilename(title="Select PacMan.exe", filetypes=[("PacMan.exe", "PacMan.exe"), ("Programs", "*.exe")])
        if p:
            self.load(os.path.normpath(p))

    def _write_error(self, e):
        messagebox.showerror(APP_TITLE, "Could not write PacMan.exe:\n%s\n\nClose the game if it is running. "
                             "If the game is installed under Program Files, run this tool as administrator." % e)

    def apply(self):
        path = self.path_var.get()
        try:
            backup = core.apply(path, self._collect_options())
        except core.UnsupportedBuild as e:
            messagebox.showerror(APP_TITLE, str(e))
            return
        except OSError as e:
            self._write_error(e)
            return
        self.load(path)
        messagebox.showinfo(APP_TITLE, "Patches applied.\n\nA copy of the original is kept as:\n%s" % backup)

    def restore(self):
        path = self.path_var.get()
        try:
            changed = core.restore(path)
        except core.UnsupportedBuild as e:
            messagebox.showerror(APP_TITLE, str(e))
            return
        except OSError as e:
            self._write_error(e)
            return
        self.load(path)
        messagebox.showinfo(APP_TITLE, "The original PacMan.exe has been restored." if changed else "PacMan.exe is already original.")

    def reset_left(self):
        try:
            reset_window_left()
        except OSError as e:
            messagebox.showerror(APP_TITLE, "Could not write the registry value:\n%s" % e)
            return
        self.refresh_registry()


def main():
    root = tk.Tk()
    root.title(APP_TITLE)
    root.resizable(False, False)
    app = App(root)
    app.load(find_game_exe())
    app.refresh_registry()
    if "--selftest" in sys.argv:
        root.update()
        # exercise the option round trip without touching any file
        app._show_options(core.Options(120, True, "on", True, True, 1.2))
        assert app._collect_options() == core.Options(120, True, "on", True, True, 1.2), app._collect_options()
        root.destroy()
        return 0
    root.mainloop()
    return 0


if __name__ == "__main__":
    sys.exit(main())
