"""Zip each board's Gerbers + drill files together with the assembly README."""
import os
import zipfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FAB = os.path.join(ROOT, "fab")

for board in ("Transmitter", "Receiver"):
    src = os.path.join(FAB, board)
    dst = os.path.join(FAB, f"{board}_gerbers.zip")
    with zipfile.ZipFile(dst, "w", zipfile.ZIP_DEFLATED) as z:
        for f in sorted(os.listdir(src)):
            z.write(os.path.join(src, f), f)
        z.write(os.path.join(ROOT, "README.md"), "README.md")
    print("wrote", dst)
