# PyInstaller hook — collect all pyttsx3 driver modules.
# Without this, PyInstaller misses the dynamically-imported SAPI5 driver
# and the frozen exe produces no speech on Windows.

from PyInstaller.utils.hooks import collect_submodules

hiddenimports = collect_submodules("pyttsx3.drivers")
