"""Linux network status and Wi-Fi control, independent from the Qt UI."""
from __future__ import annotations

import getpass
import hashlib
import json
import shutil
import socket
import subprocess
from collections.abc import Callable
from dataclasses import dataclass


class NetworkControlError(RuntimeError):
    pass


@dataclass(frozen=True)
class NetworkInterface:
    name: str
    address: str


@dataclass(frozen=True)
class WifiNetwork:
    ssid: str
    signal: int
    security: str
    connected: bool = False


@dataclass(frozen=True)
class NetworkSnapshot:
    hostname: str
    username: str
    interfaces: tuple[NetworkInterface, ...]

    @property
    def primary_address(self) -> str | None:
        for preferred in ("eth0", "enp", "end", "wlan0", "wlp"):
            for interface in self.interfaces:
                if interface.name == preferred or interface.name.startswith(preferred):
                    return interface.address
        return self.interfaces[0].address if self.interfaces else None

    @property
    def ssh_command(self) -> str:
        address = self.primary_address or "<not connected>"
        return f"ssh {self.username}@{address}"


Runner = Callable[..., subprocess.CompletedProcess]


class NetworkManager:
    def __init__(self, runner: Runner | None = None):
        self._run = runner or subprocess.run

    def snapshot(self) -> NetworkSnapshot:
        interfaces: list[NetworkInterface] = []
        if shutil.which("ip"):
            result = self._execute(
                ["ip", "-j", "-4", "address", "show", "up"],
                timeout=8,
            )
            try:
                data = json.loads(result.stdout)
            except json.JSONDecodeError as exc:
                raise NetworkControlError("Could not read network addresses.") from exc
            for item in data:
                name = item.get("ifname", "")
                if name == "lo":
                    continue
                for address in item.get("addr_info", []):
                    if address.get("family") == "inet" and address.get("local"):
                        interfaces.append(NetworkInterface(name, address["local"]))
        else:
            # Development fallback for non-Linux systems.
            try:
                address = socket.gethostbyname(socket.gethostname())
                if address and not address.startswith("127."):
                    interfaces.append(NetworkInterface("network", address))
            except OSError:
                pass
        return NetworkSnapshot(
            hostname=socket.gethostname(),
            username=getpass.getuser(),
            interfaces=tuple(interfaces),
        )

    def scan_wifi(self) -> list[WifiNetwork]:
        self._require_nmcli()
        result = self._execute(
            [
                "nmcli",
                "--terse",
                "--escape",
                "yes",
                "--fields",
                "IN-USE,SSID,SIGNAL,SECURITY",
                "device",
                "wifi",
                "list",
                "--rescan",
                "yes",
            ],
            timeout=20,
        )
        networks: dict[str, WifiNetwork] = {}
        for line in result.stdout.splitlines():
            fields = _split_nmcli(line)
            if len(fields) < 4:
                continue
            active, ssid, signal, security = fields[:4]
            if not ssid:
                continue
            try:
                strength = max(0, min(100, int(signal)))
            except ValueError:
                strength = 0
            candidate = WifiNetwork(
                ssid=ssid,
                signal=strength,
                security=security or "Open",
                connected=active.strip() == "*",
            )
            previous = networks.get(ssid)
            if previous is None or candidate.signal > previous.signal:
                networks[ssid] = candidate
        return sorted(
            networks.values(),
            key=lambda item: (not item.connected, -item.signal, item.ssid.casefold()),
        )

    def connect_wifi(
        self,
        ssid: str,
        password: str = "",
        security: str = "",
        interface: str = "wlan0",
    ) -> NetworkSnapshot:
        self._require_nmcli()
        ssid = ssid.strip()
        if not ssid:
            raise NetworkControlError("Select a Wi-Fi network first.")

        security_upper = security.upper()
        is_open = security_upper in ("", "OPEN", "--") and not password
        if "802.1X" in security_upper or "EAP" in security_upper:
            raise NetworkControlError(
                "Enterprise Wi-Fi is not supported yet. "
                "Use an open or WPA/WPA2/WPA3 Personal network."
            )
        if not is_open and not password:
            raise NetworkControlError("Enter the Wi-Fi password.")

        # Do not allow `device wifi connect` to reuse an incomplete profile.
        # An incomplete secured profile produces the key-mgmt error reported by
        # NetworkManager. This profile is owned and safely replaced by the HMI.
        profile = f"CNC-HMI-{hashlib.sha256(ssid.encode()).hexdigest()[:12]}"
        profiles = self._execute(
            [
                "nmcli",
                "--terse",
                "--escape",
                "yes",
                "--fields",
                "NAME",
                "connection",
                "show",
            ],
            timeout=10,
        )
        existing = {
            _split_nmcli(line)[0]
            for line in profiles.stdout.splitlines()
            if line
        }
        if profile in existing:
            self._execute(
                ["nmcli", "connection", "delete", "id", profile],
                timeout=10,
            )

        self._execute(
            [
                "nmcli",
                "connection",
                "add",
                "type",
                "wifi",
                "ifname",
                interface,
                "con-name",
                profile,
                "ssid",
                ssid,
            ],
            timeout=15,
        )
        if not is_open:
            key_management = (
                "sae"
                if "WPA3" in security_upper and "WPA2" not in security_upper
                else "wpa-psk"
            )
            self._execute(
                [
                    "nmcli",
                    "connection",
                    "modify",
                    "id",
                    profile,
                    "802-11-wireless-security.key-mgmt",
                    key_management,
                    "802-11-wireless-security.psk",
                    password,
                ],
                timeout=15,
                secret=password,
            )
        self._execute(
            [
                "nmcli",
                "--wait",
                "30",
                "connection",
                "up",
                "id",
                profile,
                "ifname",
                interface,
            ],
            timeout=40,
            secret=password,
        )
        return self.snapshot()

    def _require_nmcli(self) -> None:
        if shutil.which("nmcli") is None:
            raise NetworkControlError(
                "NetworkManager is unavailable; Wi-Fi cannot be configured."
            )

    def _execute(
        self,
        command: list[str],
        *,
        timeout: int,
        secret: str = "",
    ) -> subprocess.CompletedProcess:
        try:
            result = self._run(
                command,
                capture_output=True,
                text=True,
                timeout=timeout,
                check=False,
            )
        except (OSError, subprocess.TimeoutExpired) as exc:
            raise NetworkControlError(f"Network command failed: {exc}") from exc
        if result.returncode != 0:
            detail = (result.stderr or result.stdout or "Unknown error").strip()
            if secret:
                detail = detail.replace(secret, "••••••••")
            raise NetworkControlError(detail)
        return result


def _split_nmcli(line: str) -> list[str]:
    fields: list[str] = []
    current: list[str] = []
    escaped = False
    for character in line:
        if escaped:
            current.append(character)
            escaped = False
        elif character == "\\":
            escaped = True
        elif character == ":":
            fields.append("".join(current))
            current = []
        else:
            current.append(character)
    current.append("\\") if escaped else None
    fields.append("".join(current))
    return fields
