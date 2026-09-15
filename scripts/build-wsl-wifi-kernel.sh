#!/bin/sh
# Build only. Does not change .wslconfig or restart WSL.
set -eu
source_dir=${1:?Pass the extracted Microsoft WSL kernel source directory}
cd "$source_dir"
zcat /proc/config.gz > .config
scripts/config --enable WIRELESS --enable WLAN --enable CFG80211 \
    --enable MAC80211 --enable WLAN_VENDOR_REALTEK --enable RTL8XXXU \
    --enable RTL8XXXU_UNTESTED --enable RFKILL \
    --disable DEBUG_INFO --disable DEBUG_INFO_BTF --disable DEBUG_INFO_BTF_MODULES \
    --set-str EXTRA_FIRMWARE rtlwifi/rtl8192eu_nic.bin \
    --set-str EXTRA_FIRMWARE_DIR /lib/firmware \
    --set-str LOCALVERSION '-microsoft-standard-WSL2-poketrader'
make olddefconfig
for option in WIRELESS WLAN CFG80211 MAC80211 RTL8XXXU; do
    grep -qx "CONFIG_${option}=y" .config
done
make -j6 bzImage
printf '%s\n' "Built: $source_dir/arch/x86/boot/bzImage"
