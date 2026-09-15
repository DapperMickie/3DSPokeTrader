#!/bin/sh
set -eu
cd "$(dirname "$0")/.."
binary=$(mktemp /tmp/poketrader-test-XXXXXX)
trap 'rm -f "$binary"' EXIT
cc -std=gnu11 -Wall -Wextra -Werror -I3ds/include \
  tests/native.c 3ds/source/hash.c 3ds/source/files.c 3ds/source/http.c -o "$binary"
"$binary"
