---
title: Workhorse Headless Server
topics:
  - infrastructure
  - linux
  - headless-server
  - systemd
  - security-hardening
  - homelab
skills:
  - audit-headless-server
summary: >
  Architecture and operational reference for workhorse, a headless Ubuntu 24.04
  server (ThinkPad T490) serving as Docker host, SSH target, LLM inference node,
  file server, and VM host. Covers service inventory, network topology, security
  posture, and maintenance procedures.
aliases:
  - workhorse server
  - headless ubuntu server
  - homelab server
  - t490 server
  - lan server architecture
related:
  - municipal-data-pipeline-patterns
last-updated: 2026-10-28
---

# Workhorse Headless Server

## Overview

Workhorse is a Lenovo ThinkPad T490 (i7-8665U, 48GB RAM, 600GB NVMe) running Ubuntu 24.04 in headless mode (multi-user.target). It serves as the central infrastructure node for development, AI workloads, and home automation.

Previously ran a full GNOME desktop with NoMachine remote access. Migrated to headless on 2026-10-26 after neo (MacBook, A18 Pro) took over as the primary GUI device. The migration removed ~900 packages and freed ~10GB RAM that the GUI stack consumed.

> **Note:** Concrete IPs and subnets are stored locally in `lan-config.env`, not in this repo. Placeholders below use `${VAR_NAME}` notation; resolve from that file.

## Hardware

| Component | Spec |
|-----------|------|
| CPU | Intel i7-8665U (4c/8t, 1.9GHz base, 4.8GHz boost) |
| RAM | 48GB DDR4 (upgraded from 16GB) |
| Storage | 1TB NVMe (60GB root LUKS + 863GB /home LUKS + 7.4GB swap + 529MB /boot + 99MB EFI) |
| GPU | Intel UHD 620 (i915 only; MX250 blacklisted) |
| Network | Intel Gigabit Ethernet (no WiFi interface active) |
| Power | Always on AC; optimized for uptime, not battery life |

## Network Topology

```
Internet
  │
  ├── Tailscale mesh (${WORKHORSE_TAILSCALE_IP})
  │     ├── neo (${NEON_TAILSCALE_IP}) - primary client
  │     └── thin-client (${THINCLIENT_TAILSCALE_IP}) - secondary
  │
  └── LAN (${LAN_SUBNET})
        ├── router/asus (192.168.50.1) - ASUS wireless router, DHCP server
        ├── workhorse (${WORKHORSE_LAN_IP}) - ethernet, br0 bridge
        ├── neo (${NEO_LAN_IP}) - Wi-Fi
        ├── win11-autocad VM (${WIN11_LAN_IP}) - bridged via br0
        └── other LAN devices
```

Workhorse's physical NIC (`enp0s31f6`) is enslaved to a bridge (`br0`) via NetworkManager. The bridge carries workhorse's own LAN IP and gives the Windows VM its own LAN address. Access is SSH-only (pubkey, no password auth). VS Code Remote SSH and Claude Code are the primary interfaces from neo.

### DHCP Reservations

All infrastructure hosts have static DHCP reservations on the ASUS router, so LAN IPs survive reboots and lease expiry.

| Host | MAC | Reserved IP |
|------|-----|-------------|
| workhorse | `F8:75:A4:53:4A:89` | ${WORKHORSE_LAN_IP} |
| neo | `6A:5E:AE:25:66:F4` | ${NEO_LAN_IP} |
| win11-autocad | `52:54:00:06:34:A7` | ${WIN11_LAN_IP} |

### SSH Aliases

SSH config aliases on workhorse and neo for quick access:

| Alias | Target | User |
|-------|--------|------|
| `neo` / `neo-lan` | neo (Tailscale / LAN) | thomas |
| `win11` / `win` | Windows VM (LAN) | thomas |
| `asus` / `router` | ASUS router (LAN) | cornelius |
| `thinclient` / `tc` | thin-client | thomas |

## Service Inventory

### System Services

| Service | Purpose | Ports |
|---------|---------|-------|
| sshd | Remote access | 22 (all interfaces) |
| docker + containerd | Container runtime | localhost:8000 (proxy) |
| tailscaled | VPN mesh | 443, 63883 (Tailscale interface) |
| ollama | Local LLM inference | localhost:11434 |
| postgresql 16 | Database | localhost:5433 |
| smbd/nmbd | File sharing (LAN only) | 139, 445 (LAN subnet) |
| libvirtd | VM management (socket-activated); win11-autocad autostarts | n/a |
| NetworkManager | Network (br0 bridge, wired only) | n/a |
| cron | Scheduled scrapers | n/a |
| fail2ban | SSH brute-force protection | n/a |
| fwupd | Firmware updates | n/a |
| unattended-upgrades | Security patches + auto-reboot | n/a |
| smartmontools | NVMe SMART monitoring | n/a |

### User Services (thomas, lingering enabled)

| Service | Purpose |
|---------|---------|
| obsidian-sync | Continuous vault sync (obsidian-headless) |
| assistant-restart | Discord bot webhook (Docker compose) |
| ssh-agent | Standalone key management (replaced gnome-keyring) |
| ai-detector-recalibrate.timer | Monthly SlopOrNot recalibration |

### Maintenance Timers

| Timer | Schedule | Purpose |
|-------|----------|---------|
| docker-prune.timer | Sun 3 AM | Prune images/containers older than 7 days |
| workhorse-health-check.timer | Mon 7 AM | Services, disk, SMART, temps, Tailscale status |
| backup-env-files.timer | Sun 2 AM | GPG-encrypted backup of all repo .env files |
| fstrim.timer | Weekly | NVMe TRIM |
| smartd | Weekly | NVMe SMART health checks |

Scripts live in `/home/thomas/maintenance/`. Installed via `install-maintenance.sh`.

## Security Posture

### Firewall (UFW)

```
22/tcp          ALLOW   Anywhere           # SSH
Anywhere        ALLOW   on tailscale0      # All Tailscale traffic
139,445/tcp     ALLOW   ${LAN_SUBNET}      # SMB LAN only
Anywhere        ALLOW   on virbr0          # VM bridge
```

Default: deny incoming, allow outgoing.

### SSH Hardening

- Password authentication disabled (pubkey only)
- fail2ban: aggressive mode, 3 retries, 1-hour ban, 10-minute window

### Disk Encryption

Full disk encryption with TPM2 auto-unlock via clevis-initramfs. Both LUKS volumes unlock in the initramfs before systemd starts; no passphrase needed for unattended boot.

| Partition | Mapping | Type | Mount | TPM2 |
|-----------|---------|------|-------|------|
| nvme0n1p4 (60G) | `root_crypt` | LUKS2 + ext4 | `/` | clevis + systemd-cryptenroll |
| nvme0n1p1 (863G) | `home_crypt` | LUKS2 + ext4 | `/home` | clevis + systemd-cryptenroll |
| nvme0n1p3 (7.4G) | `swap_crypt` | plain dm-crypt | `[SWAP]` | random key per boot |
| nvme0n1p5 (529M) | n/a | ext4 | `/boot` | unencrypted |
| nvme0n1p2 (99M) | n/a | vfat | `/boot/efi` | unencrypted |

Key details:
- Clevis TPM2 bindings sealed to PCR 7 (Secure Boot state). Both volumes have clevis tokens (initramfs) and systemd-cryptenroll tokens (fallback).
- `home_crypt` has `initramfs` option in crypttab so clevis processes it in the initrd alongside root.
- LUKS header backup for root at `/home/root-luks-header.img`. Root filesystem backup at `/home/root-backup/`.
- Threat model: data-at-rest (drive theft). `/boot` is unencrypted; prolonged physical access with Secure Boot compromise is out of scope.
- dracut was evaluated and reverted (dependency cascade on Ubuntu 24.04). clevis-initramfs is the working solution.
- **Kernel hook**: `/etc/kernel/postinst.d/zz-clevis-rebind` automatically re-binds clevis TPM2 on both volumes after kernel installs, preventing PCR drift from breaking auto-unlock.

## Kernel Tuning

| Parameter | Value | Rationale |
|-----------|-------|-----------|
| vm.swappiness | 10 | Server with 48GB RAM; prefer keeping data in memory |

Config: `/etc/sysctl.d/99-server-tuning.conf`

## Maintenance Procedures

### Automatic Maintenance

Unattended-upgrades handles security patches automatically with:
- Unused kernel package removal enabled
- Unused dependency removal enabled
- Auto-reboot at 4 AM when a reboot-required patch is applied
- Clevis TPM2 re-bind runs automatically on kernel installs (before reboot)

The weekly health check (`workhorse-health-check.timer`) monitors: systemd services, disk usage, NVMe SMART health and wear, CPU temps, Tailscale connectivity and key expiry, Docker state. Results logged to journal:

```bash
journalctl -u workhorse-health-check --no-pager -n 50
```

Encrypted .env backups run weekly to `~/backups/env/` (GPG symmetric, AES256). Keeps last 30.

### Manual Updates

For manual upgrades:

```bash
sudo apt update && sudo DEBIAN_FRONTEND=noninteractive apt upgrade -y
```

Always use `DEBIAN_FRONTEND=noninteractive` since there is no terminal for debconf prompts in automated contexts.

### Docker Container Management

The assistant bot auto-deploys via systemd timer polling for new commits:

```bash
docker ps                           # check health
docker compose -f ~/repos/assistant/docker-compose.yml logs -f  # tail logs
```

Docker prune runs weekly (Sun 3 AM), removing images and containers older than 7 days.

### VM Management

Windows 11 Pro VM (win11-autocad, build 26200/24H2) for AutoCAD. Bridged to LAN via br0, autostarts with libvirtd. Debloated: ads, telemetry, Copilot, Recall, widgets, and bloatware removed.

| Setting | Value |
|---------|-------|
| vCPU | 4 (host-passthrough) |
| RAM | 8 GB |
| Disk | 60GB qcow2 (virtio, cache=writeback, io=threads) |
| Network | bridge (br0), DHCP reservation at ${WIN11_LAN_IP} |
| Display | SPICE on localhost:${VM_SPICE_PORT} (emergency fallback) |
| Access | SSH (`ssh win11`), RDP from neo (Microsoft Remote Desktop) |
| Shared storage | virtiofs to `/home/thomas/repos/cad` |

The VM runs OpenSSH Server (automatic start, pubkey auth). Workhorse and neo both have key-based SSH access. The VM also has outbound SSH keys authorized on workhorse and neo (`thomas@win11-autocad`).

```bash
virsh list --all                     # check state
virsh start win11-autocad            # manual start (normally autostarts)
virsh shutdown win11-autocad         # clean ACPI shutdown
ssh win11 hostname                   # SSH access (preferred)
```

Emergency SPICE console (if SSH and RDP both break):

```bash
# From neo:
ssh -L 5900:127.0.0.1:${VM_SPICE_PORT} workhorse
# Then connect SPICE/VNC viewer to localhost:5900
```

Note: the SSH session to the VM runs as a non-elevated user (UAC). For operations requiring admin rights (HKLM registry writes, service management), use a SYSTEM scheduled task:

```powershell
$action = New-ScheduledTaskAction -Execute "cmd.exe" -Argument "/c <command>"
$principal = New-ScheduledTaskPrincipal -UserId "SYSTEM" -RunLevel Highest
Register-ScheduledTask -TaskName "AdminTask" -Action $action -Principal $principal -Force
Start-ScheduledTask -TaskName "AdminTask"
Start-Sleep -Seconds 5
Unregister-ScheduledTask -TaskName "AdminTask" -Confirm:$false
```

Polkit rule (`/etc/polkit-1/rules.d/50-libvirt.rules`) grants the `libvirt` group passwordless VM management. No sudo needed for daily operations.

### Swap Troubleshooting

Swap uses ephemeral LUKS (random key per boot). If `swapon --show` is empty after reboot:

```bash
# Check crypttab references correct PARTUUID
cat /etc/crypttab
blkid /dev/nvme0n1p3
# Manually open and activate
sudo cryptsetup open --type plain --key-file /dev/urandom /dev/nvme0n1p3 swap_crypt
sudo mkswap /dev/mapper/swap_crypt
sudo swapon /dev/mapper/swap_crypt
```

### TPM2 / Disk Encryption

The kernel postinst hook (`/etc/kernel/postinst.d/zz-clevis-rebind`) handles re-binding automatically on kernel updates. Manual re-bind is only needed after firmware updates or Secure Boot changes:

```bash
# Check current clevis bindings
sudo clevis luks list -d /dev/nvme0n1p4
sudo clevis luks list -d /dev/nvme0n1p1

# Re-bind (removes old binding, creates new one sealed to current PCR values)
sudo clevis luks unbind -d /dev/nvme0n1p4 -s <slot>
sudo clevis luks bind -d /dev/nvme0n1p4 tpm2 '{"pcr_ids":"7"}'
# Repeat for /dev/nvme0n1p1

# Rebuild initramfs after any clevis changes
sudo update-initramfs -u -k all
```

If both clevis and systemd-cryptenroll tokens break, passphrase fallback is available on console (keyslot 0 on both volumes).

To verify unattended boot worked after reboot:

```bash
journalctl -b -u 'systemd-cryptsetup@*' --no-pager
# Both root_crypt and home_crypt should show "already active"
# (unlocked by clevis in initramfs before systemd started)
```

### Journal Management

Capped at 100MB (`/etc/systemd/journald.conf`). Check usage:

```bash
journalctl --disk-usage
```

### Tailscale

Key expiry disabled (personal tailnet, single user). Auto-update enabled (check and apply). No manual key rotation needed.

## What Was Removed (2026-10-26 Migration)

Preserved here for context if rollback is ever needed:

- **Display**: GNOME 46, GDM3, Mutter, XFCE 4 (NX virtual session)
- **Remote desktop**: NoMachine 9.10.3 (all user services, scripts, sudoers)
- **Audio**: PipeWire, PulseAudio, WirePlumber
- **Apps**: All flatpaks (Firefox, Discord, Slack, Spotify, Thunderbird, Inkscape), LibreOffice, Rhythmbox, Shotwell, Remmina, Transmission
- **Printing**: CUPS, hplip, 15 printer drivers
- **Bluetooth**: bluez stack
- **X server**: xserver-xorg-core, xwayland, nvidia driver
- **Input**: IBus, gnome-keyring (replaced by standalone ssh-agent)
- **Misc**: Apport, whoopsie, update-manager GUI, GNOME games

Rollback: `sudo systemctl set-default graphical.target && sudo apt install ubuntu-desktop && reboot`

## Monitoring

- NVMe SMART monitoring via smartmontools (weekly checks, alerting on degradation)
- Weekly health check timer covers services, disk, temps, Tailscale, Docker
- Netconsole configured to stream kmsg to thin-client for hard-freeze diagnosis
- No centralized log aggregation (journald only, local)
- No uptime monitoring beyond Tailscale peer status and health check timer
