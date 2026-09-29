"""Copy the license texts of everything bundled into the exe into
release\\app\\HeadFocus\\licenses.

Run by installer\\build.bat. Apache 2.0 and friends require shipping the license
text with redistributed binaries.
"""

import shutil
import sys
from importlib import metadata
from pathlib import Path

OUT = Path(__file__).resolve().parent.parent / "release" / "app" / "HeadFocus" / "licenses"
OUT.mkdir(parents=True, exist_ok=True)

copied = 0
for dist in metadata.distributions():
    name = dist.metadata["Name"]
    if name.lower() in {"pip", "setuptools", "pyinstaller", "pyinstaller-hooks-contrib", "altgraph", "packaging", "pefile", "pywin32-ctypes"}:
        continue  # build tools, not shipped
    for file in dist.files or []:
        if "license" in file.name.lower() or "notice" in file.name.lower() or "copying" in file.name.lower():
            src = Path(dist.locate_file(file))
            if src.is_file():
                shutil.copyfile(src, OUT / f"{name}-{file.name}")
                copied += 1

python_license = Path(sys.base_prefix) / "LICENSE.txt"
if python_license.exists():
    shutil.copyfile(python_license, OUT / "Python-LICENSE.txt")
    copied += 1

print(f"Collected {copied} license files into {OUT}")
