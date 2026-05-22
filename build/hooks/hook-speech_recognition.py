# PyInstaller hook — SpeechRecognition stores language model data files
# that must be bundled with the frozen exe.

from PyInstaller.utils.hooks import collect_data_files, collect_submodules

datas = collect_data_files("speech_recognition")
hiddenimports = collect_submodules("speech_recognition")
