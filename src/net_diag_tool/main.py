import typer
import os
from rich.console import Console
from rich.table import Table
from net_diag_tool.core.logger import setup_logger
from net_diag_tool.config.settings import get_settings
from net_diag_tool.modules.network.diagnostics import NetworkDiagnostics
from net_diag_tool.modules.system.health import SystemHealthMonitor
import time

# Initialize components
app = typer.Typer(name="netdiag")
console = Console()
logger = setup_logger("main")
settings = get_settings()

@app.command()
def monitor_system():
    """
    Launches the real-time System Health Monitor Dashboard.
    """
    from net_diag_tool.modules.system.health import SystemHealthMonitor
    monitor = SystemHealthMonitor()
    console.print("[bold green]Launching System Monitor Dashboard... (Press Ctrl+C to exit)[/bold green]")
    time.sleep(1)
    monitor.dashboard()

@app.command()
def run_diagnostics(
    full: bool = typer.Option(False, "--full", "-f", help="Run comprehensive system and network diagnostics"),
    save_report: bool = typer.Option(True, help="Save the output to a JSON/HTML report")
):
    """
    Run the standard diagnostic suite.
    """
    console.print(f"[bold green]Starting {settings.APP_NAME}...[/bold green]")
    logger.info("Starting diagnostic session")

    results = {}
    tool = NetworkDiagnostics()
    sys_monitor = SystemHealthMonitor() # Use new monitor for static metrics too

    # 1. Local Network Info
    console.print("[yellow]Gathering Local Network Info...[/yellow]")
    results['local_info'] = tool.get_local_network_info()
    console.print(f"Hostname: {results['local_info'].get('hostname')}")
    console.print(f"Active Connections: {results['local_info'].get('active_connections_count')}")

    # 2. Network Checks (Ping)
    console.print(f"[yellow]Pinging Targets ({settings.PING_TARGET_PRIMARY}, {settings.PING_TARGET_SECONDARY})...[/yellow]")
    results['ping_primary'] = tool.ping_host(settings.PING_TARGET_PRIMARY)
    results['ping_secondary'] = tool.ping_host(settings.PING_TARGET_SECONDARY)
    
    # 3. HTTP Check
    console.print("[yellow]Checking Internet Access (HTTP)...[/yellow]")
    results['internet_http'] = tool.check_http_status("https://www.google.com")

    # 4. System Checks
    console.print("[yellow]Running System Checks...[/yellow]")
    # Use the new monitor's methods but just get snapshot
    results['system'] = {
        "cpu": sys_monitor.get_cpu_metrics(),
        "memory": sys_monitor.get_memory_metrics(),
        "disk": sys_monitor.get_disk_metrics()
    }
    
    # 5. Full Mode Extras
    if full:
        console.print("[bold cyan]Running Detailed Diagnostics (Full Mode)...[/bold cyan]")
        
        # DNS
        console.print("[yellow]Detailed DNS Lookup...[/yellow]")
        results['dns_primary'] = tool.dns_lookup("google.com")
        
        # Bandwidth
        console.print("[yellow]Testing Bandwidth...[/yellow]")
        results['bandwidth'] = tool.bandwidth_test()
        
        # Port Scan (Localhost or Gateway)
        # For safety/demo, we scan localhost or a known safe target. 
        # scanning settings.PING_TARGET_PRIMARY (8.8.8.8) is not polite.
        # We will skip port scan in automated run unless specified target, 
        # or scan localhost.
        console.print("[yellow]Scanning Local Ports...[/yellow]")
        results['localhost_scan'] = tool.port_scan("localhost", ports=[22, 80, 443, 8080, 3306])

    # Display Summary Table
    table = Table(title="Diagnostic Summary")
    table.add_column("Check", style="cyan")
    table.add_column("Status", style="magenta")
    table.add_column("Details", style="green")

    # Ping 1
    p1 = results['ping_primary']
    status_p1 = "[green]PASS[/green]" if p1['success'] else "[red]FAIL[/red]"
    table.add_row(f"Ping {p1['host']}", status_p1, f"Loss: {p1['packet_loss_percent']}%, Latency: {p1.get('avg_latency_ms')}ms")

    # HTTP
    http = results['internet_http']
    status_http = "[green]PASS[/green]" if http['is_active'] else "[red]FAIL[/red]"
    table.add_row("Internet (HTTP)", status_http, f"Code: {http.get('status_code')} Time: {http.get('response_time_ms')}ms")

    # System
    sys = results['system']
    # CPU
    cpu_data = sys.get('cpu', {})
    table.add_row("CPU Usage", "INFO", f"{cpu_data.get('total_usage')}%")
    
    # Memory
    mem_data = sys.get('memory', {})
    table.add_row("Memory Usage", "INFO", f"{mem_data.get('percent')}% Used")
    
    # Disk (Show first disk or aggregate)
    disks = sys.get('disk', [])
    if disks:
         d = disks[0]
         table.add_row(f"Disk ({d.get('mountpoint')})", "INFO", f"{d.get('percent')}% Used")

    console.print(table)

    # Save Report
    if save_report:
        try:
            # We can use the tool's export function or the original reporter.
            # The tool has a built-in export now which is nice.
            path = tool.export_report(results, format="html")
            console.print(f"[bold blue]Report saved to: {path}[/bold blue]")
        except Exception as e:
            console.print(f"[bold red]Failed to save report: {e}[/bold red]")

@app.command()
def info():
    """Show tool configuration and version info."""
    console.print(f"app_name: {settings.APP_NAME}")
    console.print(f"env: {settings.APP_ENV}")
    console.print(f"log_level: {settings.LOG_LEVEL}")

@app.command()
def analyze_logs(
    log_file: str = typer.Argument(None, help="Path to the log file to analyze. Optional if --discover is used."),
    fmt: str = typer.Option("auto", "--format", help="Log format (auto, apache, nginx, syslog)"),
    tail: bool = typer.Option(False, "--tail", help="Live monitor the log file"),
    report: bool = typer.Option(True, "--report/--no-report", help="Generate HTML report"),
    discover: bool = typer.Option(False, "--discover", help="Auto-discover common log files")
):
    """
    Analyze server logs or monitor them in real-time.
    """
    from net_diag_tool.modules.logs.analyzer import LogAnalyzer
    
    if discover:
        logs = LogAnalyzer.auto_discover_logs()
        if not logs:
            console.print("[red]No common logs found.[/red]")
            return
        
        console.print("[cyan]Found logs:[/cyan]")
        for i, log in enumerate(logs):
            console.print(f"{i+1}. {log}")
            
        choice = typer.prompt("Select log to analyze", type=int)
        if 0 < choice <= len(logs):
            log_file = str(logs[choice-1])
        else:
            return

    if not log_file or not os.path.exists(log_file):
        console.print(f"[bold red]Error: File not found: {log_file} (or no file specified)[/bold red]")
        return

    analyzer = LogAnalyzer(log_file, log_format=fmt)
    
    if tail:
        analyzer.tail_live()
    else:
        console.print(f"[green]Analyzing {log_file}...[/green]")
        analyzer.load_data()
        
        # Display Summary
        stats = analyzer.analyze_http_logs()
        if stats:
             table = Table(title="Top 5 IPs")
             table.add_column("IP")
             table.add_column("Count")
             for ip, count in list(stats['top_ips'].items())[:5]:
                 table.add_row(ip, str(count))
             console.print(table)
             
             console.print(f"Total Lines: {analyzer.stats['total_lines']}")
             console.print(f"Potential Attacks: [red]{stats['potential_attacks_count']}[/red]")
             
        if report:
             path = analyzer.export_report()
             console.print(f"[bold blue]Report saved to: {path}[/bold blue]")

@app.command()
def monitor_services(
    config: str = typer.Option(None, "--config", "-c", help="Path to services.json config"),
    interval: int = typer.Option(60, "--interval", "-i", help="Check interval in seconds")
):
    """
    Monitor status of defined services (HTTP, TCP, DNS).
    """
    from net_diag_tool.modules.services.checker import ServiceHealthChecker
    
    checker = ServiceHealthChecker(config_file=config)
    
    if not checker.services:
        console.print("[yellow]No services specific in config.[/yellow]")
        if typer.confirm("Would you like to run the configuration wizard now?", default=True):
             configure()
             # Reload checker
             checker = ServiceHealthChecker(config_file=config)
             if not checker.services:
                 return
        else:
             return
        
    console.print(f"[green]Starting Service Monitor (Interval: {interval}s)...[/green]")
    checker.monitor_continuously(interval=interval)

@app.command()
def configure():
    """
    Interactive setup wizard to add services to monitor.
    """
    from pathlib import Path
    import json
    
    # Point to the correct config location inside src/net_diag_tool/config
    config_path = Path(__file__).parent / "config" / "services.json"
    
    # Load existing
    if config_path.exists():
        try:
            with open(config_path, 'r') as f:
                config = json.load(f)
        except:
            config = {"services": []}
    else:
        config = {"services": []}
        
    console.print(f"[bold cyan]NetDiag Configuration Wizard[/bold cyan]")
    console.print(f"Current services: {len(config.get('services', []))}")
    
    while True:
        choice = typer.prompt("Do you want to (a)dd a service, (l)ist services, or (e)xit?", default="e")
        
        if choice.lower() == 'a':
            name = typer.prompt("Service Name (e.g. My Website)")
            stype = typer.prompt("Type (http, tcp, dns, api)", default="http")
            
            service = {"name": name, "type": stype}
            
            if stype == "http":
                service["url"] = typer.prompt("URL")
                service["expected_status"] = int(typer.prompt("Expected Status", default="200"))
            elif stype == "tcp":
                service["host"] = typer.prompt("Host")
                service["port"] = int(typer.prompt("Port"))
            elif stype == "dns":
                service["host"] = typer.prompt("Domain to resolve")
            
            service["check_interval"] = int(typer.prompt("Check Interval (seconds)", default="60"))
            
            config["services"].append(service)
            console.print(f"[green]Added {name}![/green]")
            
        elif choice.lower() == 'l':
            for s in config["services"]:
                console.print(f"- {s['name']} ({s['type']})")
                
        elif choice.lower() == 'e':
            break
            
    # Save
    with open(config_path, 'w') as f:
        json.dump(config, f, indent=4)
        
    console.print(f"[bold green]Configuration saved to {config_path}[/bold green]")

if __name__ == "__main__":
    app()
