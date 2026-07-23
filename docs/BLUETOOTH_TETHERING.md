# Bluetooth Internet sharing

CryptoGotchi uses the phone as a Bluetooth Network Access Point and NetworkManager as a PAN User (`panu`). Pairing and Internet sharing are separate steps.

## Normal procedure

1. Keep the phone unlocked.
2. Open CryptoGotchi **Settings → Open phone pairing mode**.
3. Select CryptoGotchi from the phone and accept the matching code.
4. Enable Bluetooth tethering on Android, or Personal Hotspot with Bluetooth on iPhone.
5. Scan phones and press **Connect internet**.

## v0.7.0 activation behavior

The privileged helper:

- creates a fresh NetworkManager Bluetooth `panu` profile without binding an interface name;
- disables autoconnect so a missing phone cannot delay boot;
- requests DHCP over IPv4 and disables IPv6 on the PAN profile;
- marks the connection as metered;
- retries activation three times;
- confirms that NetworkManager created an active Bluetooth device and assigned IPv4;
- prints recent NetworkManager Bluetooth/DHCP errors when activation fails.

## Dashboard diagnostics

After scanning, use the phone’s **Diagnostics** button. The report appears below the Bluetooth section and includes pairing state, visible Bluetooth services, active NetworkManager connections and recent PAN/DHCP errors.

## Command-line diagnostics

```bash
sudo /usr/local/sbin/cryptogotchi-bluetooth-helper diagnose AA:BB:CC:DD:EE:FF
sudo systemctl status bluetooth NetworkManager cryptogotchi-bluetooth-agent --no-pager -l
sudo journalctl -u NetworkManager --since '-5 minutes' --no-pager
```

## Common causes

- Bluetooth tethering was not enabled after pairing.
- The phone has no upstream Wi-Fi/mobile data connection.
- The phone was locked during the first profile connection.
- Android/iOS did not expose the NAP service yet; toggle tethering off/on and retry.
- A stale profile exists from an older release; v0.7.0 deletes and recreates only CryptoGotchi’s profile.
