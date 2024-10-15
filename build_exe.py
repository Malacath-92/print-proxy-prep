import sys
import argparse
import subprocess
from pathlib import Path

from util import open_folder


BASE_DIR = Path(__file__).parent.resolve()
DIST_DIR = BASE_DIR / "dist"

EXE_NAME = Path("print-proxy-prep.exe")


def run_nuitka(debug, package):
    nuitka_args = [
        sys.executable,
        "-m",
        "nuitka",
        f"{BASE_DIR / 'main.py'}",
        "--standalone",
        "--enable-plugin=pyqt6",
        "--output-filename=print-proxy-prep",
        "--output-dir=dist",
        f"--windows-icon-from-ico={BASE_DIR / 'proxy.png'}",
        "--noinclude-unittest-mode=allow",
    ]

    if not debug:
        nuitka_args.append("--windows-console-mode=disable")
    else:
        nuitka_args.append("--include-package=debugpy")

    if package:
        nuitka_args.extend(["--onefile", "--standalone"])

    subprocess.check_call(nuitka_args)


def main():
    parser = argparse.ArgumentParser(
        description="Build print-proxy-prep.exe, run from project root"
    )
    parser.add_argument(
        "--debug", action="store_true", help="Whether to build debug exe."
    )
    parser.add_argument(
        "--package",
        action="store_true",
        help="Whether to build a single exe or a folder with dependencies.",
    )
    args = parser.parse_args()

    run_nuitka(args.debug, args.package)

    print(f"exe successfully built at {DIST_DIR / EXE_NAME}")
    open_folder(DIST_DIR)


if __name__ == "__main__":
    main()
