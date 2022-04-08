"""This script copy and package Qzone3TG and dependencies into pyz using :external+python:mod:`zipapp`.
"""

import argparse as ap
import subprocess as sp
from pathlib import Path
from shutil import copy, move, rmtree


def sp_retval(cmd: str) -> str:
    """run a subprocess and get returns as str."""
    p = sp.run(cmd.split(), shell=True, capture_output=True)
    p.check_returncode()
    r = p.stdout.decode().removesuffix("\n")
    print(f"$ {cmd}", f"\n> {r}" if r else "", sep="")
    return r


def check_tools():
    """check if subprocess executables are available."""
    sp_retval("pip --version")
    sp_retval("npm --version")


def inst_pip_deps():
    """Install dependencies in `workdir`/.venv"""
    DEPDIR.mkdir(exist_ok=True, parents=True)

    args = ["pip", "install", CONTEXT.as_posix(), "-t", DEPDIR.as_posix(), "-i", INDEX]
    print(f"$ {' '.join(args)}")
    p = sp.run(args, stdin=sp.PIPE, capture_output=False)
    p.check_returncode()

    for p in DEPDIR.iterdir():
        if p.is_dir() and p.stem == ".dist-info":
            rmtree(p, ignore_errors=True)

    main = DEPDIR / SRC / "__main__.py"
    dest = DEPDIR / "__main__.py"
    print(f"$ cp {main.as_posix()} {dest.as_posix()}")
    copy(main, dest)

    return DEPDIR


def inst_node_deps():
    """install node nodules"""
    args = ["npm", "install", "--no-optional", "--no-fund"]
    WORKDIR.mkdir(parents=True, exist_ok=True)
    copy(PACKAGE, WORKDIR)
    print(f"$ cp {PACKAGE.as_posix()} {WORKDIR.as_posix()}")
    print(f"{WORKDIR.as_posix()} $ {' '.join(args)}")
    p = sp.run(args, shell=True, capture_output=False, cwd=WORKDIR)
    p.check_returncode()
    (tp := WORKDIR / PACKAGE.name).unlink()
    (tpl := tp.with_stem("package-lock")).unlink()
    print(f"{WORKDIR.as_posix()} $ rm {tp.as_posix()} {tpl.as_posix()}")


def mv_binary():
    """move dir with pyd files inside out of DEPDIR"""
    bins = [".pyd", ".so"]

    for p in DEPDIR.iterdir():
        if (
            p.is_file()
            and p.suffix in bins
            or p.is_dir()
            and next(filter(lambda p: p.suffix in bins, p.rglob("*")), False)
        ):
            dest = WORKDIR / p.name
            if dest.exists():
                if dest.is_dir():
                    rmtree(dest)
                else:
                    dest.unlink()
            move(p, dest)
            print(f"$ mv {p.as_posix()} {dest.as_posix()}")


def pack_app():
    """package app with zipapp"""
    from zipapp import create_archive

    assert (DEPDIR / "__main__.py").exists()
    dest = WORKDIR / OUTNAME
    create_archive(DEPDIR, dest, interpreter=INTERPRETER, compressed=True)
    return dest


def clean_deps():
    """clean workspace if necessary."""
    print(f"$ rm -r {DEPDIR.as_posix()}")
    rmtree(DEPDIR, ignore_errors=True)


def zip_workdir(outpath: Path):
    from zipfile import ZipFile

    print(f"$ zip {WORKDIR.as_posix()} -o {outpath.as_posix()}")
    with ZipFile(outpath, "w") as zf:
        for p in WORKDIR.rglob("*"):
            zf.write(p, p.relative_to(WORKDIR).as_posix())


def main(stage: int, clean: bool = False, _zip: Path | None = None):
    if stage < 1:
        check_tools()
        inst_node_deps()

    if stage < 2:
        inst_pip_deps()
        mv_binary()

    if stage < 3:
        pack_app()

    if clean or _zip:
        clean_deps()

    if _zip:
        zip_workdir(_zip)


if __name__ == "__main__":
    parser = ap.ArgumentParser(description=__doc__)
    parser.add_argument("context", type=Path, default=Path("."))
    parser.add_argument("-i", "--index", type=str, default="https://pypi.org/simple")
    parser.add_argument("-n", "--package-json", type=Path, default=Path("package.json"))
    parser.add_argument("-o", "--outname", type=str, default="app.pyz")
    parser.add_argument("-p", "--python", type=str)
    parser.add_argument("-s", "--src", type=str, default="qzone3tg")
    parser.add_argument("-w", "--workdir", type=Path, default=Path("run"))
    parser.add_argument("-z", "--zip", type=Path)
    parser.add_argument("--clean", action="store_true")
    parser.add_argument("--stage", type=int, default=0)

    args = parser.parse_args()
    INDEX: str = args.index
    PACKAGE: Path = args.package_json
    OUTNAME: str = args.outname
    CONTEXT: Path = args.context
    INTERPRETER: str | None = args.python
    SRC: str = args.src
    WORKDIR: Path = args.workdir

    DEPDIR = WORKDIR / ".venv"
    main(args.stage, clean=args.clean, _zip=args.zip)
