# AGENTS.md

## BeeRef

A simple reference image viewer. Python 3.9-3.12, PyQt6, packaged with setuptools
(`pyproject.toml`), dev install via `pip install -e .` into `.venv`.

### Windows launcher icon (beeref.exe)

`.venv\Scripts\beeref.exe` is pip's distlib-generated windowed launcher
(template `w64.exe` + appended archive). The appended archive (a
`#!...pythonw.exe` shebang + zip containing `__main__.py`) is appended to the
stub and is what the stub locates at runtime via the PE overlay offset.

**NEVER patch `beeref.exe` directly with `rcedit`** (or Resource Hacker etc.)
to set its icon: rcedit drops the appended archive, and the launcher then dies
with `Fatal error in launcher: Unable to find appended archive`. Symptom:
`beeref.exe` exits immediately with code 1.

To fix a corrupted launcher: regenerate it with
`.venv\Scripts\python.exe -m pip install -e .`

To set the icon safely, use `tools\set_exe_icon.ps1` (run from anywhere in the
repo). It patches only the PE stub with `tools\rcedit-x64.exe`, then re-appends
the original appended archive. Re-run it after every `pip install -e .`
(installs regenerate the launcher and wipe the icon). Do not call rcedit
directly.

Note: the running window's taskbar icon comes from `logo.png` at runtime
(`beeref\__main__.py`), independent of the exe icon.
