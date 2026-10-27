---
name: audit-headless-server
topics:
  - infrastructure
  - linux
  - headless-server
  - security-hardening
summary: >
  Step-by-step audit procedure for the workhorse headless server covering
  service health, security posture, resource usage, and cleanup opportunities.
references:
  - articles/infrastructure/workhorse-headless-server.md
last-updated: 2026-10-26
---

# Audit Headless Server

## Prerequisites

- SSH access to workhorse (pubkey auth)
- sudo privileges (cached or available via terminal)
- Familiarity with the service inventory in the companion article

## Steps

### 1. Verify critical services

```bash
# System services
systemctl is-active sshd docker tailscaled ollama cron fail2ban smbd

# User services (as thomas)
systemctl --user is-active obsidian-sync assistant-restart ssh-agent

# Docker containers
docker ps --format '{{.Names}}: {{.Status}}'

# Tailscale connectivity
tailscale status | head -5
```

All must report `active` or `Up`. Investigate any failures before continuing.

### 2. Check resource usage

```bash
# RAM
free -h

# Swap
swapon --show

# Disk
df -h / /home

# Journal size (should be under 100MB)
journalctl --disk-usage

# Recent OOM kills
journalctl -k --since "7 days ago" | grep -i "oom\|out of memory"
```

Flag: RAM usage over 40GB sustained, swap usage over 2GB, root disk over 80%, any OOM kills.

### 3. Audit network exposure

```bash
# All listening ports
sudo ss -tlnp | sort

# Firewall rules
sudo ufw status numbered
```

Expected listeners: sshd (22), smbd (139/445), tailscaled (443, 63883 on tailscale0), ollama (127.0.0.1:11434), postgresql (127.0.0.1:5432/5433), docker-proxy (127.0.0.1:8000), dnsmasq (192.168.122.1:53), systemd-resolved (127.0.0.53:53, 127.0.0.54:53).

Any listener not on this list or not bound to localhost/tailscale0/virbr0 needs investigation.

### 4. Check security services

```bash
# fail2ban status
sudo fail2ban-client status sshd

# Recent SSH auth failures
journalctl -u sshd --since "24 hours ago" | grep -c "Failed\|Invalid"

# Unattended upgrades last run
cat /var/log/unattended-upgrades/unattended-upgrades.log | tail -5
```

### 5. Check for pending updates

```bash
apt list --upgradable 2>/dev/null | grep -v "^Listing"
```

Apply with `sudo DEBIAN_FRONTEND=noninteractive apt upgrade -y` if any are security-relevant.

### 6. Scan for service drift

```bash
# Running system services (should be ~15-20)
systemctl list-units --type=service --state=running --no-pager | grep loaded | wc -l

# Enabled user services (should be ~12)
systemctl --user list-unit-files --state=enabled | grep -c enabled

# Any GUI processes that shouldn't exist?
ps aux | grep -iE 'gnome|pipewire|pulse|gdm|mutter|nx|xorg|wayland' | grep -v grep
```

### 7. Verify encryption

```bash
# Home encryption
cryptsetup status home_crypt

# Swap encryption
swapon --show
cat /etc/crypttab
```

Both should be active. If swap is missing, see troubleshooting in the companion article.

### 8. Check cron jobs

```bash
crontab -l
```

Verify scraper schedules are current and log files aren't growing unbounded:

```bash
du -sh ~/repos/yimby.watchdog/data/*.log 2>/dev/null
```

## Constraints

- Never install GUI packages on workhorse (headless by design)
- Never use zenity or other GUI tools for sudo; use terminal prompt or cached credentials
- Always use `DEBIAN_FRONTEND=noninteractive` for apt operations in non-interactive contexts
- SMB must stay LAN-only (UFW rule restricts to ${LAN_SUBNET})
- Do not expose ollama or PostgreSQL beyond localhost

## Outputs

A brief status report covering:
- Service health (all up / issues found)
- Resource usage (RAM, swap, disk)
- Security posture (fail2ban stats, unexpected listeners)
- Pending actions (updates, log cleanup, drift fixes)
