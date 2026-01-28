import platform
import subprocess
import socket
import re
import time
import requests
import dns.resolver
import psutil
import threading
import json
import netifaces
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Dict, Any, List, Optional, Union
from pathlib import Path
from datetime import datetime
from jinja2 import Template
from rich.console import Console
from rich.progress import Progress, SpinnerColumn, TextColumn, BarColumn, DownloadColumn, TransferSpeedColumn

from net_diag_tool.core.logger import setup_logger
from net_diag_tool.config.settings import get_settings

logger = setup_logger(__name__)
settings = get_settings()
console = Console()

class NetworkDiagnostics:
    """
    Production-ready Network Diagnostics Module.
    Includes tools for Ping, Traceroute, DNS, Port Scanning, HTTP Checks, and Bandwidth Testing.
    """
    
    def __init__(self):
        self.os_type = platform.system().lower()
        self.reports_dir = Path("reports")
        self.reports_dir.mkdir(exist_ok=True)

    def ping_host(self, hostname: str, count: int = 4, timeout: int = 5) -> Dict[str, Any]:
        """
        Pings a host using the system's native ping command.
        
        Args:
            hostname: Target host to ping.
            count: Number of packets to send.
            timeout: Timeout in seconds for the command.
            
        Returns:
            Dict containing success status, packet loss, avg latency, and raw output.
        """
        logger.info(f"Pinging {hostname} with {count} packets...")
        
        param_count = '-n' if self.os_type == 'windows' else '-c'
        param_wait = '-w' if self.os_type == 'windows' else '-W'
        
        # Windows uses milliseconds for wait, Linux uses seconds usually, but some variants differ.
        # Keeping it simple: typical Windows default is fine, Linux needs appropriate flag.
        # For production robustness, we construct the command carefully.
        
        command = ['ping', param_count, str(count), hostname]
        if self.os_type == 'windows':
            command.extend([param_wait, str(timeout * 1000)]) # ms
        else:
            # Linux ping -W is timeout in seconds usually
             command.extend([param_wait, str(timeout)])
             
        try:
            # Run command
            result = subprocess.run(
                command, 
                stdout=subprocess.PIPE, 
                stderr=subprocess.PIPE, 
                text=True, 
                timeout=timeout * count + 5 # Generous timeout for execution
            )
            
            output = result.stdout
            success = result.returncode == 0
            
            # Parse Output
            packet_loss = 100.0
            avg_latency = None
            
            # Regex for packet loss
            loss_match = re.search(r'(\d+)% packet loss', output) or re.search(r'Lost = \d+ \((\d+)% loss\)', output)
            if loss_match:
                packet_loss = float(loss_match.group(1))
            
            # Regex for latency (Average)
            # Windows: "Average = 12ms"
            # Linux: "min/avg/max/mdev = 10.1/12.4/15.2/0.5 ms"
            if self.os_type == 'windows':
                latency_match = re.search(r'Average = (\d+)ms', output)
            else:
                latency_match = re.search(r'/(\d+\.?\d*)/', output) # Captures the avg in the slash group
                
            if latency_match:
                avg_latency = float(latency_match.group(1))

            return {
                "host": hostname,
                "success": success,
                "packet_loss_percent": packet_loss,
                "avg_latency_ms": avg_latency,
                "output": output if not success else "Ping successful" # truncate for successful usually
            }
            
        except subprocess.TimeoutExpired:
            logger.error(f"Ping to {hostname} timed out execution.")
            return {"host": hostname, "success": False, "error": "Command Execution Timeout"}
        except Exception as e:
            logger.error(f"Ping failed: {e}")
            return {"host": hostname, "success": False, "error": str(e)}

    def traceroute(self, hostname: str, max_hops: int = 30) -> Dict[str, Any]:
        """
        Runs a traceroute to the target host.
        
        Args:
            hostname: Target host.
            max_hops: Max number of hops.
            
        Returns:
            Dict containing list of hops and status.
        """
        logger.info(f"Running traceroute to {hostname}...")
        
        tool = 'tracert' if self.os_type == 'windows' else 'traceroute'
        command = [tool]
        
        if self.os_type == 'windows':
             command.extend(['-h', str(max_hops), '-d', hostname]) # -d prevents DNS resolution for speed
        else:
             command.extend(['-m', str(max_hops), '-n', hostname])
             
        hops = []
        try:
            # Using Popen to stream output if needed, but run is simpler for now
            result = subprocess.run(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
            
            lines = result.stdout.splitlines()
            # Basic parsing logic
            for line in lines:
                # Windows regex:  1    <1 ms    <1 ms    <1 ms  192.168.1.1
                # Linux regex:  1  192.168.1.1  0.123 ms  0.111 ms  0.105 ms
                if re.match(r'^\s*\d+', line):
                    parts = line.split()
                    if len(parts) >= 2:
                        hop_num = parts[0]
                        # Find the IP address (last usually or middle) - simple heuristic
                        ip_match = re.search(r'(\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3})', line)
                        ip = ip_match.group(1) if ip_match else "*"
                        
                        # Find latencies
                        latencies = re.findall(r'(\d+)\s*ms', line) or re.findall(r'(\d+\.\d+)\s*ms', line)
                        
                        hops.append({
                            "hop": hop_num,
                            "ip": ip,
                            "latencies": latencies
                        })
            
            return {
                "host": hostname,
                "success": result.returncode == 0,
                "hops": hops,
                "hop_count": len(hops)
            }
        except Exception as e:
            logger.error(f"Traceroute failed: {e}")
            return {"host": hostname, "success": False, "error": str(e)}

    def dns_lookup(self, hostname: str) -> Dict[str, Any]:
        """
        Performs DNS resolution (A, AAAA, MX, NS).
        """
        logger.info(f"Performing DNS lookup for {hostname}...")
        results = {}
        resolver = dns.resolver.Resolver()
        
        # Try to use Google DNS for consistency if local fails, or just use system default
        # resolver.nameservers = ['8.8.8.8'] 
        
        record_types = ['A', 'AAAA', 'MX', 'NS']
        
        for r_type in record_types:
            try:
                answers = resolver.resolve(hostname, r_type)
                results[r_type] = [r.to_text() for r in answers]
            except dns.resolver.NoAnswer:
                results[r_type] = []
            except dns.resolver.NXDOMAIN:
                return {"host": hostname, "error": "Domain does not exist"}
            except Exception as e:
                results[r_type] = f"Error: {str(e)}"

        try:
             nameserver = resolver.nameservers[0] if resolver.nameservers else "System Default"
        except:
             nameserver = "Unknown"

        return {
            "host": hostname,
            "records": results,
            "nameserver_used": nameserver
        }

    def check_port(self, hostname: str, port: int, timeout: int = 3) -> Dict[str, Any]:
        """
        Checks if a TCP port is open.
        """
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.settimeout(timeout)
        start_time = time.time()
        try:
            s.connect((hostname, port))
            conn_time = (time.time() - start_time) * 1000 # ms
            s.close()
            return {"port": port, "status": "OPEN", "time_ms": round(conn_time, 2)}
        except socket.timeout:
            return {"port": port, "status": "FILTERED/TIMEOUT", "time_ms": None}
        except ConnectionRefusedError:
            return {"port": port, "status": "CLOSED", "time_ms": None}
        except Exception as e:
            return {"port": port, "status": f"ERROR: {e}", "time_ms": None}
        finally:
            s.close()

    @staticmethod
    def get_default_gateway() -> Optional[str]:
        """Detects the default gateway IP."""
        try:
            gws = netifaces.gateways()
            return gws['default'][netifaces.AF_INET][0]
        except Exception:
            return None

    @staticmethod
    def get_dns_servers() -> List[str]:
        """Detects system DNS servers (Cross-platform attempt)."""
        # This is tricky cross-platform, simplifying to gateway + known reliable
        return ["8.8.8.8", "1.1.1.1"]

    def run_all(self, targets: List[str] = None):
        """Runs all diagnostics on targets."""
        if not targets:
            # Smart Default: Gateway + 8.8.8.8
            gw = self.get_default_gateway()
            targets = [gw] if gw else []
            targets.append("8.8.8.8")
            
        self.console.print(f"[bold blue]Pinging Targets ({', '.join(targets)})...[/bold blue]")
        results = {}
        
        for target in targets:
            self.console.print(f"  Pinging {target}...", end="")
            ping_res = self.ping_host(target)
            results[target] = ping_res
            if ping_res['status'] == 'up':
                self.console.print(f" [green]UP[/green] ({ping_res.get('avg_latency_ms')}ms)")
            else:
                self.console.print(" [red]DOWN[/red]")
                
        # Bandwidth check if full run (handled in main usually, but simple check here)
        return results

    def port_scan(self, hostname: str, ports: List[int] = None) -> Dict[str, Any]:
        """
        Scans a list of ports using threading.
        WARNING: Ethical use only.
        """
        if ports is None:
            ports = [80, 443, 22, 21, 25, 3389, 3306, 5432, 8080]
            
        logger.info(f"Scanning ports on {hostname}: {ports}")
        results = {}
        
        # Threaded scan
        with ThreadPoolExecutor(max_workers=min(10, len(ports))) as executor:
            future_to_port = {executor.submit(self.check_port, hostname, port): port for port in ports}
            for future in as_completed(future_to_port):
                port = future_to_port[future]
                try:
                    data = future.result()
                    results[port] = data
                except Exception as e:
                    results[port] = {"status": "ERROR", "error": str(e)}
                    
        return {"host": hostname, "scan_results": results}

    def check_http_status(self, url: str, timeout: int = 10) -> Dict[str, Any]:
        """
        Checks HTTP/HTTPS status, headers, and SSL.
        """
        if not url.startswith("http"):
            url = f"http://{url}"
            
        logger.info(f"Checking HTTP Status for {url}...")
        try:
            start_time = time.time()
            response = requests.get(url, timeout=timeout, allow_redirects=True)
            elapsed_time = (time.time() - start_time) * 1000 # ms
            
            return {
                "url": url,
                "status_code": response.status_code,
                "reason": response.reason,
                "response_time_ms": round(elapsed_time, 2),
                "is_active": response.ok,
                "redirects": [r.url for r in response.history],
                "server_header": response.headers.get("Server", "Unknown"),
                "content_type": response.headers.get("Content-Type", "Unknown")
            }
        except requests.exceptions.SSLError:
            return {"url": url, "error": "SSL Certificate Error", "is_active": False}
        except requests.exceptions.ConnectionError:
            return {"url": url, "error": "Connection Failed", "is_active": False}
        except requests.exceptions.Timeout:
            return {"url": url, "error": "Request Timed Out", "is_active": False}
        except Exception as e:
            return {"url": url, "error": str(e), "is_active": False}

    def bandwidth_test(self, test_url: str = "http://speedtest.tele2.net/1MB.zip") -> Dict[str, Any]:
        """
        Measures download speed.
        """
        logger.info(f"Starting bandwidth test using {test_url}...")
        chunk_size = 1024
        try:
            start_time = time.time()
            response = requests.get(test_url, stream=True, timeout=10)
            if not response.ok:
                return {"error": f"Failed to connect to test server. Status: {response.status_code}"}
                
            total_length = int(response.headers.get('content-length', 0))
            downloaded = 0
            
            # Use Rich Progress
            with Progress(
                SpinnerColumn(),
                TextColumn("[progress.description]{task.description}"),
                BarColumn(),
                DownloadColumn(),
                TransferSpeedColumn(),
                console=console,
                transient=True # Disappear after done
            ) as progress:
                task = progress.add_task("[cyan]Downloading test file...", total=total_length or None)
                
                for chunk in response.iter_content(chunk_size=chunk_size):
                    if chunk:
                        downloaded += len(chunk)
                        progress.update(task, advance=len(chunk))
                        
            end_time = time.time()
            duration = end_time - start_time
            if duration == 0: duration = 0.01
            
            # Mbps = (MB * 8) / seconds
            size_mb = downloaded / (1024 * 1024)
            speed_mbps = (size_mb * 8) / duration
            
            return {
                "downloaded_bytes": downloaded,
                "duration_seconds": round(duration, 2),
                "speed_mbps": round(speed_mbps, 2)
            }
            
        except Exception as e:
             logger.error(f"Bandwidth test error: {e}")
             return {"error": str(e)}

    def get_local_network_info(self) -> Dict[str, Any]:
        """
        Retrieves interfaces, IP, Gateway, DNS (OS dependent).
        """
        info = {
            "hostname": socket.gethostname(),
            "interfaces": {},
            "active_connections_count": 0
        }
        
        # Interfaces
        addrs = psutil.net_if_addrs()
        for name, snics in addrs.items():
            info["interfaces"][name] = []
            for snic in snics:
                if snic.family == socket.AF_INET:
                    info["interfaces"][name].append({
                        "ip": snic.address,
                        "netmask": snic.netmask,
                        "broadcast": snic.broadcast
                    })
                    
        # Active Connections (count)
        try:
            # Requires privileges potentially
            conns = psutil.net_connections(kind='inet')
            info["active_connections_count"] = len(conns)
        except Exception as e:
            info["active_connections_error"] = str(e)
            
        return info

    def continuous_monitor(self, targets: List[str], interval: int = 60, cycles: int = 3):
        """
        Monitors a list of hosts for a set number of cycles (to avoid infinite blocks in this tool execution).
        In a real service, this would verify forever or run in a daemon.
        """
        results_log = []
        try:
            with Progress(
                SpinnerColumn(),
                TextColumn("[progress.description]{task.description}"),
                BarColumn(),
                console=console
            ) as progress:
                overall_task = progress.add_task("[green]Monitoring Network...", total=cycles)
                
                for i in range(cycles):
                    cycle_results = {"timestamp": datetime.now().isoformat(), "checks": []}
                    for host in targets:
                        ping_res = self.ping_host(host, count=1)
                        status = "UP" if ping_res['success'] else "DOWN"
                        cycle_results["checks"].append({"host": host, "status": status, "latency": ping_res.get("avg_latency_ms")})
                        
                        color = "green" if status == "UP" else "red"
                        console.print(f"[{datetime.now().strftime('%H:%M:%S')}] {host}: [{color}]{status}[/{color}] - {ping_res.get('avg_latency_ms', 'N/A')}ms")
                    
                    results_log.append(cycle_results)
                    progress.update(overall_task, advance=1)
                    if i < cycles - 1:
                        time.sleep(interval)
        except KeyboardInterrupt:
            console.print("[yellow]Monitoring stopped by user.[/yellow]")
            
        return results_log

    def export_report(self, results: Dict[str, Any], format: str = "html") -> str:
        """
        Exports results to a file.
        """
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"report_{timestamp}.{format}"
        filepath = self.reports_dir / filename
        
        if format == "json":
            with open(filepath, 'w') as f:
                json.dump(results, f, indent=4, default=str)
        elif format == "html":
            # Simple Jinja2 Template
            template_str = """
            <!DOCTYPE html>
            <html>
            <head>
                <title>Network Diagnostic Report</title>
                <style>
                    body { font-family: sans-serif; margin: 2rem; background: #f4f4f9; }
                    .card { background: white; padding: 1.5rem; margin-bottom: 1rem; border-radius: 8px; box-shadow: 0 2px 4px rgba(0,0,0,0.1); }
                    h1 { color: #333; }
                    .success { color: green; }
                    .failure { color: red; }
                    pre { background: #eee; padding: 10px; border-radius: 4px; overflow-x: auto; }
                </style>
            </head>
            <body>
                <h1>Network Diagnostic Report</h1>
                <p>Generated: {{ timestamp }}</p>
                
                {% for category, data in results.items() %}
                <div class="card">
                    <h2>{{ category|title }}</h2>
                    <pre>{{ data | tojson(indent=2) }}</pre>
                </div>
                {% endfor %}
            </body>
            </html>
            """
            template = Template(template_str)
            content = template.render(results=results, timestamp=timestamp)
            with open(filepath, 'w', encoding='utf-8') as f:
                f.write(content)
                
        return str(filepath)

# ---------------------------------------------------------
# Main Execution for Demonstration
# ---------------------------------------------------------
def main():
    """
    Demonstrates the full capabilities of the Network Diagnostic Tool.
    """
    tool = NetworkDiagnostics()
    console.print("[bold blue]Network Diagnostic Tool - Comprehensive Test[/bold blue]")
    
    results = {}

    # 1. Local Info
    console.print("\n[bold]1. Local Network Info[/bold]")
    results['local_info'] = tool.get_local_network_info()
    console.print(results['local_info'])

    # 2. Ping
    console.print("\n[bold]2. Pinging Google (8.8.8.8)[/bold]")
    results['ping'] = tool.ping_host("8.8.8.8")
    console.print(results['ping'])

    # 3. DNS Lookup
    console.print("\n[bold]3. DNS Lookup (github.com)[/bold]")
    results['dns'] = tool.dns_lookup("github.com")
    console.print(results['dns'])

    # 4. Port Scan
    console.print("\n[bold]4. Port Scan (scanme.nmap.org)[/bold]")
    # Only scanning a few ports to be polite and fast
    results['port_scan'] = tool.port_scan("scanme.nmap.org", ports=[80, 443, 22])
    console.print(results['port_scan'])

    # 5. HTTP Status
    console.print("\n[bold]5. HTTP Status (httpstat.us/200)[/bold]")
    results['http'] = tool.check_http_status("https://httpstat.us/200")
    console.print(results['http'])
    
    # 6. Traceroute
    console.print("\n[bold]6. Traceroute (1.1.1.1)[/bold]")
    results['traceroute'] = tool.traceroute("1.1.1.1", max_hops=10) # Limited hops for speed in demo
    console.print(f"Traceroute finished with {len(results['traceroute'].get('hops', []))} hops")

    # 7. Bandwidth Test
    console.print("\n[bold]7. Bandwidth Test[/bold]")
    results['bandwidth'] = tool.bandwidth_test()
    console.print(results['bandwidth'])

    # 8. Export
    console.print("\n[bold]8. Exporting Report[/bold]")
    path = tool.export_report(results, format="html")
    console.print(f"[green]Report saved: {path}[/green]")

if __name__ == "__main__":
    main()
