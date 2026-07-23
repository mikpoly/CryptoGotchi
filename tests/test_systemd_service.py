from pathlib import Path


def test_supplementary_groups_are_space_separated():
    service = Path("systemd/cryptogotchi.service").read_text(encoding="utf-8")
    line = next(line for line in service.splitlines() if line.startswith("SupplementaryGroups="))
    assert "," not in line
    assert line == "SupplementaryGroups=spi gpio i2c netdev video bluetooth"


def test_bluetooth_helper_is_narrowly_installed():
    install = Path("scripts/install.sh").read_text(encoding="utf-8")
    helper = Path("scripts/cryptogotchi-bluetooth-helper").read_text(encoding="utf-8")
    service = Path("systemd/cryptogotchi.service").read_text(encoding="utf-8")
    assert "/usr/local/sbin/cryptogotchi-bluetooth-helper" in install
    assert "visudo -cf" in install
    agent = Path("scripts/cryptogotchi-bluetooth-agent.py").read_text(encoding="utf-8")
    agent_service = Path("systemd/cryptogotchi-bluetooth-agent.service").read_text(encoding="utf-8")
    assert "bluetoothctl --timeout 70 pair" in helper
    assert "DisplayYesNo" in agent
    assert "cryptogotchi-bluetooth-agent.service" in install
    assert "ExecStart=/usr/local/lib/cryptogotchi/cryptogotchi-bluetooth-agent.py" in agent_service
    assert "After=network-online.target NetworkManager.service bluetooth.service cryptogotchi-bluetooth-agent.service" in service
    assert "NoNewPrivileges=false" in service
