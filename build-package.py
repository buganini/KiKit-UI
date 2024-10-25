import PyInstaller.__main__
import platform
import subprocess
import os

import kikit
kikit_base = os.path.dirname(kikit.__file__)

create_dmg = False

args = []
create_dmg_args = []
if platform.system()=="Darwin":
    args.extend(["--add-binary", f"/Applications/KiCad/KiCad.app/Contents/Frameworks/*.dylib:."])
    args.extend(["-i", 'icon.icns'])
    subprocess.run(["security", "find-identity", "-v", "-p", "codesigning"])
    codesign_identity = input("Enter the codesign identity (leave empty for no signing): ").strip()
    if codesign_identity:
        args.extend(["--codesign-identity", codesign_identity])
        create_dmg_args.extend(["--codesign", codesign_identity])
        create_dmg_args.extend(["--notarize", "notarytool-creds"])
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
    if os.path.exists("kikit-ui.dmg"):
        os.unlink("kikit-ui.dmg")
    subprocess.run([
        "create-dmg",
        "--volname", "KiKit-UI",
        "--app-drop-link", "0", "0",
        *create_dmg_args,
        "kikit-ui.dmg", "dist/kikit-ui.app"
    ])
    if codesign_identity:
        subprocess.run(["spctl", "-a", "-t", "open", "--context", "context:primary-signature", "-v", "kikit-ui.dmg"])
