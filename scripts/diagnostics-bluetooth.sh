#!/usr/bin/env bash
set -u

echo '=== Bluetooth services ==='
systemctl --no-pager --full status bluetooth.service cryptogotchi-bluetooth-agent.service 2>&1 | sed -n '1,80p'
echo
echo '=== Controller ==='
bluetoothctl show 2>&1
echo
echo '=== Paired devices ==='
bluetoothctl paired-devices 2>&1
echo
echo '=== Active NetworkManager connections ==='
nmcli -f NAME,TYPE,DEVICE,STATE connection show --active 2>&1
echo
echo '=== Agent journal ==='
journalctl -u cryptogotchi-bluetooth-agent.service -b --no-pager -n 80 2>&1
