"""Checks system libraries needed by IntelliLabel (Phase 1 'make setup')."""
import shutil
import sys

ok = True
for name, check in [
    ("tesseract (OCR fallback)", lambda: shutil.which("tesseract")),
]:
    found = check()
    print(f"[{'ok' if found else 'MISSING'}] {name}")
    ok &= bool(found)
for mod, desc in [("pyzbar.pyzbar", "libzbar0 (linear barcodes)"), ("pylibdmtx.pylibdmtx", "libdmtx (Data Matrix)"),
                  ("pymupdf", "PyMuPDF"), ("cv2", "OpenCV")]:
    try:
        __import__(mod)
        print(f"[ok] {desc}")
    except Exception as e:  # noqa: BLE001
        print(f"[MISSING] {desc}: {e}")
        ok = False
if not ok:
    print("\nSome components are missing. On Ubuntu/WSL2: sudo apt install tesseract-ocr libzbar0 libdmtx0b poppler-utils")
    sys.exit(1)
print("System check passed.")
