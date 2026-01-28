# NetDiag Suite

**NetDiag Suite** is a high-performance, asynchronous dashboard and diagnostic tool for IT Operations. It consolidates network testing, system health monitoring, service uptime tracking, and log analysis into a single zero-dependency CLI application.

## Core Capabilities

*   **Real-Time Dashboard**: Monitor CPU, Memory, Disk I/O, and Critical Services (Docker, PostgreSQL, etc.) with a TUI (Terminal User Interface).
*   **Service Monitoring**: AsyncIO-powered uptime checker for HTTP, TCP, and DNS services. Monitors hundreds of endpoints in parallel.
*   **Log Intelligence**: Auto-detects and parses Apache, Nginx, and Syslog files. specific security modules identify SQL Injection, XSS attempts, and Brute Force patterns.
*   **Network Diagnostics**: Smart routing detection, bandwidth estimation, traceroute, and multi-threaded port scanning.
*   **Persistent History**: Uses a local SQLite database to track uptime trends over time.

## Quick Start

### Option 1: Standalone Executable (Windows)
No installation required. Download `netdiag.exe` and run:

```powershell
# Setup your services (Websites, APIs, Databases)
.\netdiag.exe configure

# Start the Live Monitor
.\netdiag.exe monitor-services
```

### Option 2: Python Installation
Requires Python 3.9+.

```bash
pip install -r requirements.txt
pip install -e .

# Run
netdiag --help
```

## detailed Usage

### 1. Service Monitoring
Pulse-check your infrastructure with sub-second latency.

```bash
# Interactive setup
netdiag configure

# Start monitoring (Ctrl+C to stop)
netdiag monitor-services --interval 5
```

### 2. System Health
Launch the resources dashboard.

```bash
netdiag monitor-system
```

### 3. Log Forensics
Analyze server logs for threats and generate HTML reports.

```bash
# Auto-discover logs on system
netdiag analyze-logs --discover

# Analyze specific file and generate report
netdiag analyze-logs /var/log/nginx/access.log --report
```

### 4. Network Snapshot
Perform a connectivity audit of the local environment.

```bash
netdiag run-diagnostics --full
```

## Development

Built with:
*   **Typer** (CLI)
*   **Rich** (UI)
*   **Httpx** (Async Networking)
*   **SQLite** (Persistence)

To build the executable locally:
```bash
python build_exe.py
```

## License
MIT
