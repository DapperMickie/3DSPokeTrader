#!/bin/sh
# Install in this checkout. Does not change Wi-Fi settings or install system packages.
set -eu
cd "$(dirname "$0")/.."
python=${PYTHON:-python3}
"$python" -c 'import sys; assert sys.version_info >= (3,12), "Python 3.12 or newer is required"'
"$python" -m venv .venv
.venv/bin/python -m pip install --upgrade pip
.venv/bin/python -m pip install -e .
upstream=.deps/frlg-ldn-trade
revision=13809c21b6e992097f98453b7cbc9e2bc30bbf7c
if [ ! -e "$upstream" ]; then
    git clone https://github.com/tornadus/frlg-ldn-trade.git "$upstream"
    git -C "$upstream" checkout --detach "$revision"
fi
test "$(git -C "$upstream" rev-parse HEAD)" = "$revision" || {
    echo "Existing upstream checkout differs from the pinned revision; leave it intact and use a fresh checkout."
    exit 1
}
.venv/bin/python -m pip install -r "$upstream/requirements.txt"
printf '%s\n' 'Bridge installed. Next: pair the 3DS using the README instructions.'
