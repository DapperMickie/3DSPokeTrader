#!/bin/sh
set -eu

version="0.18.4"
archive="makerom-v${version}-ubuntu_x86_64.zip"
expected_sha256="dd596854718c195c6e3229286be485b122921715555af8ae5cf8e9a465d9f970"
install_dir="${1:-/usr/local/bin}"
download_url="https://github.com/3DSGuy/Project_CTR/releases/download/makerom-v${version}/${archive}"
work_dir="$(mktemp -d)"
trap 'rm -rf "$work_dir"' EXIT

curl --fail --location --silent --show-error "$download_url" --output "$work_dir/$archive"
printf '%s  %s\n' "$expected_sha256" "$work_dir/$archive" | sha256sum --check --status
if command -v unzip >/dev/null 2>&1; then
    unzip -q "$work_dir/$archive" -d "$work_dir/unpacked"
elif command -v busybox >/dev/null 2>&1; then
    mkdir -p "$work_dir/unpacked"
    busybox unzip -q "$work_dir/$archive" -d "$work_dir/unpacked"
elif command -v python3 >/dev/null 2>&1; then
    python3 -m zipfile -e "$work_dir/$archive" "$work_dir/unpacked"
else
    echo "A ZIP extractor (unzip, busybox, or python3) is required." >&2
    exit 1
fi
install -d "$install_dir"
install -m 0755 "$work_dir/unpacked/makerom" "$install_dir/makerom"
