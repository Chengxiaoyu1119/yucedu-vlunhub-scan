from pathlib import Path

from PyInstaller.utils.hooks import collect_data_files


def is_external_asset(source):
    parts = Path(str(source)).parts
    name = Path(str(source)).name.lower()
    return ".local-browsers" in parts or (name == "node.exe" and "driver" in parts)


# Chromium and the Node driver are staged beside the EXE. Keep only the
# Playwright protocol runtime inside the executable.
datas = [item for item in collect_data_files("playwright") if not is_external_asset(item[0])]
