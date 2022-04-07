"""This script copy and package Qzone3TG and dependencies into pyz using :external+python:mod:`zipapp`.
"""

import argparse as ap
import logging
import stat
import subprocess as sp
from pathlib import Path
from shutil import copytree, move, rmtree

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)


def sp_retval(cmd: str) -> str:
    """run a subprocess and get returns as str."""
    p = sp.run(cmd.split(), capture_output=True)
    p.check_returncode()
    r = p.stdout.decode()
    logger.info("[%s]> %s", cmd, r)
    return r


def check_tools():
    """check if subprocess executables are available."""
    sp_retval("pip --version")
    if not REQUIREMENT.exists():
        sp_retval("poetry --version")


def ensure_requirement():
    if not REQUIREMENT.exists():
        sp_retval(f"poetry export --without-hashes -o {REQUIREMENT.as_posix()}")
    assert REQUIREMENT.exists()


def inst_deps():
    """Install dependencies in `workdir`/.venv"""
    WORKDIR.mkdir(exist_ok=True)
    ensure_requirement()

    if DEPDIR.exists():
        if DEPDIR.is_dir():
            rmtree(DEPDIR)
        else:
            DEPDIR.unlink()
    copytree(SRC, DEPDIR)
    assert (DEPDIR / "__main__.py").exists()

    args = ["pip", "install", "-r", REQUIREMENT.as_posix(), "-t", DEPDIR.as_posix(), "-i", INDEX]
    p = sp.run(args, stdin=sp.PIPE, capture_output=False)
    p.check_returncode()
    logger.info("[%s]> OK", " ".join(args))

    for p in DEPDIR.iterdir():
        if p.is_dir() and p.stem == ".dist-info":
            rmtree(p, ignore_errors=True)

    return DEPDIR


def mv_pyd():
    """move dir with pyd files inside out of DEPDIR"""
    for p in DEPDIR.iterdir():
        if p.is_file() and p.stem == ".pyd" or p.is_dir() and next(p.rglob("*.pyd"), False):
            dest = WORKDIR / p.name
            if dest.exists():
                if dest.is_dir():
                    rmtree(dest)
                else:
                    dest.unlink()
            move(p, dest)
            logger.info("mv %s %s", p.as_posix(), dest.as_posix())


def pack_app():
    """package app with zipapp"""
    from zipapp import create_archive

    assert (DEPDIR / "__main__.py").exists()
    dest = WORKDIR / OUTNAME
    create_archive(DEPDIR, dest, interpreter=INTERPRETER, compressed=True)
    # dest.chmod(stat.S_IXUSR)
    return dest


def clean_deps():
    """clean workspace if necessary."""
    rmtree(DEPDIR, ignore_errors=True)
    REQUIREMENT.unlink()


def main(stage: int = 0, clean: bool = False):
    if stage < 1:
        check_tools()
        inst_deps()
        mv_pyd()

    if stage < 2:
        pack_app()

    if clean:
        clean_deps()


if __name__ == "__main__":
    parser = ap.ArgumentParser(description=__doc__)
    parser.add_argument("-i", "--index", type=str, default="https://pypi.org/simple")
    parser.add_argument("-o", "--outname", type=str, default="app.pyz")
    parser.add_argument("-p", "--python", type=str)
    parser.add_argument("-r", "--requirement", type=str, default="requirements.txt")
    parser.add_argument("-s", "--src", type=Path, default=Path("src/qzone3tg"))
    parser.add_argument("-w", "--workdir", type=Path, default=Path("run"))
    parser.add_argument("--clean", action="store_true")
    parser.add_argument("--stage", type=int, default=0)

    args = parser.parse_args()
    INDEX: str = args.index
    OUTNAME: str = args.outname
    INTERPRETER: str | None = args.python
    SRC: Path = args.src
    WORKDIR: Path = args.workdir

    REQUIREMENT: Path = WORKDIR / args.requirement
    DEPDIR = WORKDIR / ".venv"
    main(args.stage, clean=args.clean)
