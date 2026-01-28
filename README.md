# NetDiag Suite

**NetDiag Suite** is an enterprise-grade, asynchronous diagnostic toolkit for IT Operations. It is designed to provide real-time visibility into network performance, system health, and service availability through a high-performance terminal interface.

## Core Capabilities

*   **Real-Time System Telemetry**: Live TUI dashboard monitoring CPU, Memory, Disk I/O, and Critical Processes (Docker, PostgreSQL, Nginx, etc.).
*   **High-Concurrency Service Monitoring**: Powered by `AsyncIO` and `httpx`, the service monitor can check hundreds of HTTP, TCP, and DNS endpoints in parallel with sub-second precision.
*   **Log Forensics & Security**: Automated parsing of Apache, Nginx, and Syslog formats. Includes a security heuristics engine to detect SQL Injection, XSS, and Brute Force patterns.
*   **Intelligent Network Auditing**: Features smart gateway detection, bandwidth estimation, traceroute visualization, and multi-threaded port scanning.
*   **Data Persistence**: Integrated SQLite storage for historical uptime tracking and trend analysis.

## Installation

The suite is built for Python 3.9+ and can be installed directly from source.

```bash
# Clone the repository
git clone https://github.com/nurwell/netdiag-suite.git
cd netdiag-suite

# Install dependencies
pip install -r requirements.txt
pip install -e .
```

## detailed Usage

### 1. Service Availability Monitoring
Configure and monitor your critical infrastructure with persistent history.

```bash
# Interactive configuration wizard
netdiag configure

# Launch the live status board
netdiag monitor-services --interval 5
```

### 2. System Resource Dashboard
Visualize system metrics in real-time.

```bash
netdiag monitor-system
```

### 3. Log Analysis & Threat Detection
scan server logs for anomalies and generating compliance reports.

```bash
# Auto-discover logs on the host
netdiag analyze-logs --discover

# Analyze a specific log file and generate an HTML report
netdiag analyze-logs /var/log/nginx/access.log --report
```

### 4. Network Health Snapshot
Perform a comprehensive connectivity audit.

```bash
netdiag run-diagnostics --full
```

## Quality Assurance & Testing

This project adheres to strict code quality standards and includes a comprehensive test suite covering all modules.

### Running the Test Suite
We use `pytest` for unit and integration testing. The suite validates:
*   **Network Modules**: Mocked socket and HTTP interactions.
*   **Log Parsers**: RegEx accuracy against varied log formats.
*   **System Monitors**: Metric collection and anomaly detection logic.
*   **Service Checkers**: async flow control and database interactions.

To run the tests:

```bash
# Run all tests
pytest

# Run with coverage report
pytest --cov=net_diag_tool
```

### CI/CD Ready
The test suite is designed to run in CI environments (GitHub Actions, Jenkins) to ensure stability before deployment.

## Tech Stack

*   **Core**: Python 3.13+
*   **CLI Framework**: Typer
*   **UI/UX**: Rich
*   **Networking**: Httpx (Async), Netifaces
*   **Analysis**: Pandas, Matplotlib

## License
MIT License
