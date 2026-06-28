import json
import subprocess

import pytest

from cnc_controller.network import (
    NetworkControlError,
    NetworkManager,
    _split_nmcli,
)


class FakeRunner:
    def __init__(self, responses):
        self.responses = list(responses)
        self.commands = []

    def __call__(self, command, **kwargs):
        self.commands.append(command)
        return self.responses.pop(0)


def result(stdout="", stderr="", returncode=0):
    return subprocess.CompletedProcess([], returncode, stdout, stderr)


def test_nmcli_parser_handles_escaped_colons():
    assert _split_nmcli(r"*:Shop\:Floor:82:WPA2") == [
        "*",
        "Shop:Floor",
        "82",
        "WPA2",
    ]


def test_wifi_scan_sorts_connected_then_signal(monkeypatch):
    monkeypatch.setattr("cnc_controller.network.shutil.which", lambda _: "/usr/bin/nmcli")
    runner = FakeRunner(
        [result("*:Current:55:WPA2\n:Strong:90:WPA2\n:Open:20:\n")]
    )
    networks = NetworkManager(runner).scan_wifi()

    assert [item.ssid for item in networks] == ["Current", "Strong", "Open"]
    assert networks[0].connected
    assert networks[2].security == "Open"


def test_snapshot_prefers_ethernet_for_ssh(monkeypatch):
    monkeypatch.setattr("cnc_controller.network.shutil.which", lambda _: "/usr/bin/ip")
    payload = [
        {"ifname": "wlan0", "addr_info": [{"family": "inet", "local": "10.0.0.8"}]},
        {"ifname": "eth0", "addr_info": [{"family": "inet", "local": "10.0.0.4"}]},
    ]
    snapshot = NetworkManager(FakeRunner([result(json.dumps(payload))])).snapshot()

    assert snapshot.primary_address == "10.0.0.4"
    assert snapshot.ssh_command.endswith("@10.0.0.4")


def test_wifi_connect_does_not_include_password_in_error(monkeypatch):
    monkeypatch.setattr("cnc_controller.network.shutil.which", lambda _: "/usr/bin/nmcli")
    runner = FakeRunner(
        [
            result(),
            result(),
            result(stderr="bad secret-password", returncode=10),
        ]
    )

    with pytest.raises(NetworkControlError) as exc:
        NetworkManager(runner).connect_wifi("Shop", "secret-password", "WPA2")

    assert "secret-password" not in str(exc.value)
    assert "••••••••" in str(exc.value)


def test_wifi_connect_sets_key_management_before_activation(monkeypatch):
    monkeypatch.setattr("cnc_controller.network.shutil.which", lambda _: "/usr/bin/nmcli")
    runner = FakeRunner(
        [
            result(),
            result(),
            result(),
            result(),
            result("[]"),
        ]
    )

    NetworkManager(runner).connect_wifi("Shop", "password123", "WPA2")

    modify = runner.commands[2]
    activate = runner.commands[3]
    assert "802-11-wireless-security.key-mgmt" in modify
    assert "wpa-psk" in modify
    assert activate[3:6] == ["connection", "up", "id"]


def test_secured_wifi_requires_password(monkeypatch):
    monkeypatch.setattr("cnc_controller.network.shutil.which", lambda _: "/usr/bin/nmcli")

    with pytest.raises(NetworkControlError, match="password"):
        NetworkManager(FakeRunner([])).connect_wifi("Shop", "", "WPA2")
