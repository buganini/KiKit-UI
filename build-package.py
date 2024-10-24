import PyInstaller.__main__
import platform
import subprocess
import os

import kikit
kikit_base = os.path.dirname(kikit.__file__)

create_dmg = False

args = []
if platform.system()=="Darwin":
    args.extend(["--add-binary", f"/Applications/KiCad/KiCad.app/Contents/Frameworks/*.dylib:."])
    args.extend(["-i", 'icon.icns'])
    create_dmg = True
else:
    args.extend(["-i", 'icon.ico'])

args.extend(["--add-data", f"{os.path.join(kikit_base, 'resources', 'kikit.pretty')}:kikit.pretty"])

print(args)

PyInstaller.__main__.run([
    'kikit-ui.py',
    "--onedir",
    '--noconfirm',
    '--windowed',
    '--add-data=icon.ico:.',
    *args
])

if create_dmg:
    subprocess.run([
        "create-dmg",
        "--volname", "KiKit-UI",
        "--app-drop-link", "0", "0",
        "kikit-ui.dmg", "dist/kikit-ui.app"
    ])