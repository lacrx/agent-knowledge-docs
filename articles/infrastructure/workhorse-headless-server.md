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
last-updated: 2026-10-26
---

# Workhorse Headless Server

## Overview

Workhorse is a Lenovo ThinkPad T490 (i7-8665U, 48GB RAM, 600GB NVMe) running Ubuntu 24.04 in headless mode (multi-user.target). It serves as the central infrastructure node for development, AI workloads, and home automation.

Previously ran a full GNOME desktop with NoMachine remote access. Migrated to headless on 2026-10-26 after neon (MacBook, A18 Pro) took over as the primary GUI device. The migration removed ~900 packages and freed ~10GB RAM that the GUI stack consumed.

> **Note:** Concrete IPs and subnets are stored locally in `lan-config.env`, not in this repo. Placeholders below use `${VAR_NAME}` notation; resolve from that file.

## Hardware

| Component | Spec |
|-----------|------|
| CPU | Intel i7-8665U (4c/8t, 1.9GHz base, 4.8GHz boost) |
| RAM | 48GB DDR4 (upgraded from 16GB) |
| Storage | 600GB NVMe (60GB root + 540GB LUKS-encrypted /home) |
| GPU | Intel UHD 620 (i915 only; MX250 blacklisted) |
| Network | Intel Gigabit Ethernet (no WiFi interface active) |
| Power | Always on AC; optimized for uptime, not battery life |

## Network Topology

```
Internet
  │
  ├── Tailscale mesh (${WORKHORSE_TAILSCALE_IP})
  │     ├── neon (${NEON_TAILSCALE_IP}) - primary client
  │     └── thin-client (${THINCLIENT_TAILSCALE_IP}) - secondary
  │
  └── LAN (${LAN_SUBNET})
        ├── workhorse (${WORKHORSE_LAN_IP}) - ethernet
        └── other LAN devices
```

Access is SSH-only (pubkey, no password auth). VS Code Remote SSH and Claude Code are the primary interfaces from neon.

## Service Inventory

### System Services

| Service | Purpose | Ports |
|---------|---------|-------|
| sshd | Remote access | 22 (all interfaces) |
| docker + containerd | Container runtime | localhost:8000 (proxy) |
| tailscaled | VPN mesh | 443, 63883 (Tailscale interface) |
| ollama | Local LLM inference | localhost:11434 |
| postgresql (14 + 16) | Databases | localhost:5432, 5433 |
| smbd/nmbd | File sharing (LAN only) | 139, 445 (LAN subnet) |
| libvirtd | VM management (socket-activated) | n/a |
| NetworkManager | Network (wired only) | n/a |
| cron | Scheduled scrapers | n/a |
| fail2ban | SSH brute-force protection | n/a |
| fwupd | Firmware updates | n/a |
| unattended-upgrades | Security patches | n/a |

### User Services (thomas, lingering enabled)

| Service | Purpose |
|---------|---------|
| obsidian-sync | Continuous vault sync (obsidian-headless) |
| assistant-restart | Discord bot webhook (Docker compose) |
| ssh-agent | Standalone key management (replaced gnome-keyring) |
| ai-detector-recalibrate.timer | Monthly SlopOrNot recalibration |

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

- `/home` on LUKS (TPM2 auto-unlock): `home_crypt`
- Swap on plain dm-crypt with ephemeral random key: `swap_crypt`
- Root (`/`) unencrypted (boot partition)

## Kernel Tuning

| Parameter | Value | Rationale |
|-----------|-------|-----------|
| vm.swappiness | 10 | Server with 48GB RAM; prefer keeping data in memory |

Config: `/etc/sysctl.d/99-server-tuning.conf`

## Maintenance Procedures

### Applying Updates

Unattended-upgrades handles security patches automatically. For manual upgrades:

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

### VM Management

Windows 11 VM for AutoCAD:

```bash
~/.local/bin/start-win11-vm.sh      # start headless
virsh list --all                     # check state
# Connect from neon: remote-viewer spice://workhorse:${VM_SPICE_PORT}
```

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

### Journal Management

Capped at 100MB (`/etc/systemd/journald.conf`). Check usage:

```bash
journalctl --disk-usage
```

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

## Monitoring Gaps

- No centralized log aggregation (journald only, local)
- No uptime monitoring beyond Tailscale peer status
- Netconsole configured to stream kmsg to thin-client for hard-freeze diagnosis
- No SMART disk monitoring configured
