# PyInstaller hook — pycaw uses comtypes which generates Python bindings
# at runtime via ITypeLib. We force-collect comtypes submodules so the
# frozen exe can resolve COM interfaces without write access to site-packages.

from PyInstaller.utils.hooks import collect_submodules, collect_data_files

hiddenimports = (
    collect_submodules("comtypes")
    + collect_submodules("pycaw")
    + [
        "comtypes.client",
        "comtypes.automation",
        "comtypes.server",
        "comtypes.server.automation",
        "comtypes.typeinfo",
    ]
)

datas = collect_data_files("comtypes")
