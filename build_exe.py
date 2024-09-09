import PyInstaller.__main__
import platform
import subprocess

create_dmg = False

args = []
if platform.system()=="Darwin":
    args.append("--onefile")
    args.extend(["--add-binary", f"/Applications/KiCad/KiCad.app/Contents/Frameworks/*.dylib:."])
    create_dmg = True
else:
    args.append("--onedir")

print("Args", args)

PyInstaller.__main__.run([
    'kikit-ui.py',
    '--noconfirm',
    '--windowed',
    *args
])

if create_dmg:
    subprocess.run([
        "create-dmg",
        "--volname", "KiKit-UI",
        "--app-drop-link", "0", "0",
        "kikit-ui.dmg", "dist/kikit-ui.app"
    ])