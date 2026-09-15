# WSL adapter trial

This is an experimental setup for the RTL8192EU USB adapter. USB detection or a
working Wi-Fi interface does not establish compatibility with Switch trading.

## Hardware and prerequisites found

- Windows Ethernet connection is active.
- USB Wi-Fi adapter: Realtek RTL8192EU, USB ID `0bda:818b`.
- Ubuntu-18.04 runs under WSL 2.
- Installed WSL kernel: `5.15.146.1-microsoft-standard-WSL2`.
- That kernel has USB/IP support but disables `WIRELESS` and `WLAN`.
- `usbipd-win` 5.3.0 was installed and successfully attached the adapter.

## USB attachment

In Windows PowerShell, use `usbipd list` to find the adapter's current bus ID.
Bus IDs can change after reconnecting a device. Bind only the Realtek adapter.
Binding requires an administrator terminal; attachment does not.

```powershell
usbipd bind --busid 5-1
usbipd attach --wsl --busid 5-1
```

While attached, the Wi-Fi adapter belongs to WSL. Windows keeps using Ethernet.
Detach it to return it to Windows:

```powershell
usbipd detach --busid 5-1
```

## Kernel build

The build uses Microsoft's matching `linux-msft-wsl-5.15.146.1` source tag,
the running kernel configuration, and the in-tree `rtl8xxxu` driver. The script
`scripts/build-wsl-wifi-kernel.sh` enables the wireless stack and builds a kernel.
It does not activate it. Build dependencies are gcc, make, flex, bison, bc,
libssl-dev and libelf-dev. Firmware is supplied by Ubuntu's linux-firmware package.

The custom kernel retains the installed kernel's version base. It is a local
compatibility experiment, not a maintained replacement for WSL kernel updates.
WSL's custom kernel setting applies to all WSL 2 distributions on the account.

## Bridge network

The USB adapter is for the Switch link. The bridge's HTTP API uses the PC's
Ethernet connection through WSL networking. On NAT-mode WSL, LAN access from
the 3DS needs a Windows forwarding rule and firewall allowance for the bridge
port. These should target only the bridge port and private LAN, not expose
the service to the Internet.

## References

- [Microsoft USB passthrough guide](https://learn.microsoft.com/en-us/windows/wsl/connect-usb)
- [Microsoft kernel source](https://github.com/microsoft/WSL2-Linux-Kernel/tree/linux-msft-wsl-5.15.146.1)
- [Upstream adapter compatibility](https://github.com/tornadus/frlg-ldn-trade#tested-wifi-cards)

## Validated on this PC

The custom kernel boots and exposes `phy0` / `wlan0` through `rtl8xxxu`.
The driver recognized the adapter and loaded firmware revision 19.0. Firmware
had to be embedded with `CONFIG_EXTRA_FIRMWARE`; the kernel could not find
Ubuntu's firmware through the WSL root mount.

Checks completed:

- Passive scan detected 11 access points. Network names were not included in output.
- A monitor interface received 230 frames in three seconds. Packets were counted,
  not saved.
- Channel selection worked after bringing the unused managed interface down.
- The actual LDN 0.0.17 library created and activated a monitor interface and
  selected channel 1.
- All 30 bridge tests passed under WSL Python 3.12.12.
- Pinned upstream CLI, 48 record loads, party stats and receipt callback passed.

The driver reports RX calibration warnings. These tests establish basic radio
access, not Switch association, packet transmission reliability or a completed
trade. The RTL8192EU remains unverified for end-to-end trading.

## Installed locations

- Kernel source: `/opt/poketrader-wsl/WSL2-Linux-Kernel-linux-msft-wsl-5.15.146.1`
- Active kernel image: `D:\Projects\3DSPokeTrader\.tools\wsl\bzImage-firmware`
- Windows kernel selection: `C:\Users\ruste\.wslconfig`
- Python and virtual environment: `/opt/poketrader-wsl/python` and `/opt/poketrader-wsl/venv`
- Clean upstream checkout: `/opt/poketrader-wsl/upstream`
- Private pairing config: `/opt/poketrader-wsl/bridge.cfg`
- PC LAN address at setup time: `192.168.1.194`, bridge port `8765`.

Do not remove or move the active kernel image while `.wslconfig` references it.
No `.wslconfig` existed before this trial. To revert the kernel, remove only the
`kernel=` entry added by this setup, then run `wsl --shutdown`. This stops all
WSL distributions. Detach the USB adapter to return it to Windows.

## Next session

Keep an Ubuntu terminal open, then attach the adapter from Windows PowerShell.
After attachment, allow a few seconds for firmware initialization. In Ubuntu:

```sh
sudo ip link set wlan0 down
sudo iw dev
```

The `phy` number can change; use the one from `iw dev`. Keep the unused managed
interface down so it does not prevent the trading library from selecting channels.
This USB adapter is not used for Internet connectivity.

With the user's own keys available, start the live bridge in Ubuntu:

```sh
sudo install -m 0755 /mnt/d/Projects/3DSPokeTrader/scripts/wsl-nmcli-shim.sh /usr/local/bin/nmcli
sudo /opt/poketrader-wsl/venv/bin/python -m poketrader serve \
  --config /opt/poketrader-wsl/bridge.cfg \
  --upstream /opt/poketrader-wsl/upstream \
  --keys /path/to/prod.keys \
  --phy phy0
```

WSL does not run NetworkManager. The installed `nmcli` shim only accepts the
managed/unmanaged calls made by the pinned upstream project. It is appropriate
here because `wlan0` is a dedicated Switch adapter and the bridge separately
brings that interface down with `ip`.

LAN forwarding is configured and the live bridge health endpoint is reachable
from Windows through `192.168.1.194:8765`. An authenticated request returned
`PokeTrader/1` and `LIVE`; a request without a token returned HTTP 401.
A real 3DS connection and an end-to-end Switch trade are still pending.

## Live bridge configured

The user-supplied key file was copied to `/opt/poketrader-wsl/prod.keys` with
mode 0600. All four required entries were present with 16-byte values. No key
contents were printed. Key authenticity cannot be established by format checks;
a real Switch connection remains the practical validation.

The service uses `/opt/poketrader-wsl/bridge-data` for persistent transaction
records. Do not change this data directory when restarting the bridge.

Current Windows port forwarding:

- Listen: `192.168.1.194:8765`
- Destination: WSL `172.22.178.113:8765`
- Firewall rule: `PokeTrader-WSL-LAN`
- Allowed source: `192.168.1.0/24`, Ethernet interface only.

WSL's NAT address can change after restart. Update the forwarding destination to
the IPv4 address shown by `ip -4 addr show eth0` inside WSL. Do not add router
port forwarding.

The paired 3DS config is available locally at
`dist/3ds/PokeTrader/bridge.cfg`. It is excluded from Git and the public release
archives. Copy it to `/3ds/PokeTrader/bridge.cfg` on the SD card alongside the
application, then select Settings > Test & save.

To restart the live service after USB attachment:

```sh
sudo ip link set wlan0 down
sudo /opt/poketrader-wsl/venv/bin/python -m poketrader serve \
  --config /opt/poketrader-wsl/bridge.cfg \
  --data /opt/poketrader-wsl/bridge-data \
  --upstream /opt/poketrader-wsl/upstream \
  --keys /opt/poketrader-wsl/prod.keys \
  --phy phy0
```

Stop it with Ctrl+C in the terminal running the service. No automatic Windows
startup task was installed. Keep the same bridge-data directory on later runs.

To remove the forwarding, run these in an administrator PowerShell:

```powershell
netsh interface portproxy delete v4tov4 listenaddress=192.168.1.194 listenport=8765
Remove-NetFirewallRule -Name PokeTrader-WSL-LAN
```

