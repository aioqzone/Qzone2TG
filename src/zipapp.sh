#!/usr/bin/env bash

# This script aims to build the minimal Qzone2TG pyz.
# before running the script, caller should export a `requirements.txt`,
# otherwise the script will call `uv export` itself.
# `python3` and `uv` are assumed to be available.
#
# If some dependency must be compiled from source, this script can install a
# build toolchain when `INSTALL_BUILD_TOOLS=1` (apt-based systems only).
# The toolchain is only installed when the wheel-only install fails, and it is
# meant for throw-away build stages (e.g. the Dockerfile builder stage).

set -euo pipefail

if [ $# -lt 1 ]; then
    echo "usage: $0 <workdir>" >&2
    exit 1
fi

workdir=$1
mkdir -p "${workdir}"

PIP_LOCK="${workdir}/requirements.txt"
PIP_TARG="${workdir}/.venv"

# export dependencies
if [ -f requirements.txt ]; then
    mv requirements.txt "${PIP_LOCK}"
else
    uv export --format requirements-txt -q --no-annotate --no-hashes \
        --no-emit-project --no-dev --emit-index-url --locked \
        -o "${PIP_LOCK}"
fi

install_deps() {
    uv pip install --python python3 -r "${PIP_LOCK}" -t "${PIP_TARG}" \
        --no-progress --no-cache "$@"
}

install_build_tools() {
    if [ "${INSTALL_BUILD_TOOLS:-0}" != "1" ]; then
        return 1
    fi

    if ! command -v apt-get >/dev/null 2>&1; then
        echo "INSTALL_BUILD_TOOLS=1 is only supported on apt-based systems." >&2
        return 1
    fi

    local sudo_cmd=""
    if [ "$(id -u)" -ne 0 ]; then
        if command -v sudo >/dev/null 2>&1; then
            sudo_cmd="sudo"
        else
            echo "INSTALL_BUILD_TOOLS=1 requires root or sudo." >&2
            return 1
        fi
    fi

    echo "installing build toolchain..."

    ${sudo_cmd} apt-get update || return 1
    ${sudo_cmd} apt-get install -y --no-install-recommends \
        build-essential pkg-config curl ca-certificates || return 1
    ${sudo_cmd} rm -rf /var/lib/apt/lists/* || return 1

    # pydantic-core has no wheel for python 3.15 yet and needs a recent Rust.
    if ! command -v cargo >/dev/null 2>&1; then
        echo "installing Rust toolchain..."
        curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs \
            | sh -s -- -y --profile minimal --default-toolchain stable --no-modify-path \
            || return 1
        # shellcheck disable=SC1090
        . "${CARGO_HOME:-$HOME/.cargo}/env" || return 1
    fi
}

# Prefer wheels: only install a build toolchain when a source build is really
# required and INSTALL_BUILD_TOOLS=1 allows it.
if ! install_deps --no-build; then
    echo "Some dependencies have no wheel and must be built from source." >&2
    rm -rf "${PIP_TARG}"

    if ! install_build_tools; then
        echo "Build toolchain is not available." >&2
        echo "Install it manually, or set INSTALL_BUILD_TOOLS=1 to let this script" >&2
        echo "install it automatically (apt-based systems only)." >&2
        exit 1
    fi

    install_deps
fi

rm -f "${PIP_TARG}/.lock"

cp -r src/qzone3tg "${PIP_TARG}"
cp "${PIP_TARG}/qzone3tg/__main__.py" "${PIP_TARG}"

# remove requirements.txt
rm "${PIP_LOCK}"

for unittest in $(find "${PIP_TARG}" -name "test*"); do
    if [ -d "$unittest" ]; then rm -r "$unittest"; fi
done

echo "moving libs to top level..."
for depname in ${PIP_TARG}/*; do
    if [ -d $depname ]; then
        so=$(find $depname -regex '.*\.so\.?.*')
        if [[ $so != "" ]]; then
            echo "$depname: lib files detected"
            mv $depname $workdir;
        fi
    fi
done

echo "removing pycache..."
for pycache in $(find $workdir -name "__pycache__"); do
    rm -r $pycache
done

# zip app
python3 -m zipapp -o $workdir/app.pyz -c ${PIP_TARG}
rm -r ${PIP_TARG}
