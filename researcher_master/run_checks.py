"""Quick environment & dependency checks for the Researcher-Master prototype.

Run this script to verify Python, key packages, and Docker availability.
It prints actionable suggestions if something is missing.
"""
import sys
import subprocess
import importlib

REQUIRED = [
    ('fastapi', 'fastapi'),
    ('uvicorn', 'uvicorn'),
    ('pytest', 'pytest'),
]

OPTIONAL = [
    ('transformers', 'transformers'),
    ('sentence_transformers', 'sentence_transformers'),
    ('torch', 'torch'),
    ('spacy', 'spacy'),
]


def check_python():
    print(f"Python executable: {sys.executable}")
    print(f"Python version: {sys.version.split()[0]}")


def check_packages():
    ok = True
    for mod, name in REQUIRED:
        try:
            importlib.import_module(mod)
            print(f"[OK] {name}")
        except Exception:
            print(f"[MISSING] {name} - install with: pip install {name}")
            ok = False

    print('\nOptional (improves performance/quality):')
    for mod, name in OPTIONAL:
        try:
            importlib.import_module(mod)
            print(f"[OK] {name}")
        except Exception:
            print(f"[OPTIONAL MISSING] {name} - pip install {name} (or skip to use lexical fallback)")

    return ok


def check_docker():
    try:
        res = subprocess.run(["docker", "version"], capture_output=True, text=True)
        if res.returncode == 0:
            print("[OK] Docker is available")
        else:
            print("[MISSING] Docker not available or not in PATH")
    except Exception:
        print("[MISSING] Docker not available or not in PATH")


def main():
    check_python()
    print('\nChecking required packages...')
    ok = check_packages()
    print('\nChecking Docker (optional)...')
    check_docker()
    if not ok:
        print('\nSome required packages are missing. Run: pip install -r requirements.txt')
    else:
        print('\nEnvironment looks good. To run the server:')
        print('  uvicorn src.app.main:app --reload --host 127.0.0.1 --port 8000')


if __name__ == '__main__':
    main()
