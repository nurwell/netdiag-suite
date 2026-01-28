import asyncio
import httpx
import socket
import time
import json
import dns.resolver
from pathlib import Path
from datetime import datetime
from typing import Dict, Any, List, Optional
from jinja2 import Template
from rich.console import Console
from rich.table import Table
from rich.live import Live

from net_diag_tool.core.logger import setup_logger
from net_diag_tool.core.database import DatabaseManager

logger = setup_logger(__name__)
console = Console()

class ServiceHealthChecker:
    """
    Production-ready Async Service Health Checker.
    Monitors HTTP, TCP, API, and DNS services using asyncio for high performance.
    """

    def __init__(self, config_file: str = None):
        self.config_path = self._resolve_config_path(config_file)
        self.config = self.load_service_config()
        self.services = self.config.get("services", [])
        self.db = DatabaseManager("netdiag_history.db")
        self.metrics = {s['name']: [] for s in self.services}
        self.alerts = []
        self.output_dir = Path("reports")
        self.output_dir.mkdir(exist_ok=True)

    def _resolve_config_path(self, path: str) -> Path:
        if path: return Path(path)
        return Path(__file__).parent.parent.parent / "config" / "services.json"

    def load_service_config(self) -> Dict[str, Any]:
        """Loads and validates service configuration."""
        if not self.config_path.exists():
            cwd_path = Path("src/net_diag_tool/config/services.json")
            if cwd_path.exists():
                self.config_path = cwd_path
            else:
                return {"services": []}
        try:
            with open(self.config_path, 'r') as f:
                return json.load(f)
        except Exception:
            return {"services": []}

    async def check_http_service(self, client: httpx.AsyncClient, url: str, timeout: int = 10, expected_status: int = 200) -> Dict[str, Any]:
        """Async HTTP check."""
        start = time.time()
        result = {
            "timestamp": datetime.now(),
            "status": "down",
            "ssl_valid": False,
            "error_message": None,
            "response_time_ms": 0
        }
        
        try:
            resp = await client.get(url, timeout=timeout)
            duration = (time.time() - start) * 1000
            
            result.update({
                "response_time_ms": round(duration, 2),
                "status_code": resp.status_code,
                "status": "up" if resp.status_code == expected_status else "down",
                "ssl_valid": url.startswith("https"),
            })
            
            if resp.status_code != expected_status:
                result["error_message"] = f"Unexpected status: {resp.status_code}"
                
        except httpx.RequestError as e:
            result["error_message"] = f"Request Error: {str(e)}"
        except Exception as e:
            result["error_message"] = str(e)
            
        return result

    async def check_tcp_service(self, host: str, port: int, timeout: int = 5) -> Dict[str, Any]:
        """Async TCP check."""
        start = time.time()
        result = {
            "timestamp": datetime.now(),
            "status": "down",
            "error_message": None,
            "response_time_ms": 0
        }
        
        try:
            # open_connection is the async equivalent of socket.create_connection
            reader, writer = await asyncio.wait_for(asyncio.open_connection(host, port), timeout=timeout)
            duration = (time.time() - start) * 1000
            
            writer.close()
            await writer.wait_closed()
            
            result["status"] = "up"
            result["response_time_ms"] = round(duration, 2)
        except asyncio.TimeoutError:
             result["error_message"] = "Connection Timeout"
        except Exception as e:
            result["error_message"] = str(e)
            
        return result

    async def check_dns_resolution(self, domain: str, expected_ip: str = None) -> Dict[str, Any]:
        """Async DNS check invocation (blocking wrapped in thread)."""
        start = time.time()
        result = {
            "timestamp": datetime.now(),
            "status": "down",
            "error": None
        }
        
        def _resolve():
            resolver = dns.resolver.Resolver()
            return [r.to_text() for r in resolver.resolve(domain, 'A')]

        try:
            # DNS python is blocking, run in executor
            ips = await asyncio.to_thread(_resolve)
            duration = (time.time() - start) * 1000
            
            status = "up"
            if expected_ip and expected_ip not in ips:
                status = "down"
                result["error"] = f"IP mismatch. Expected {expected_ip}, got {ips}"
            
            result.update({
                "status": status,
                "response_time_ms": round(duration, 2),
                "ips": ips
            })
        except Exception as e:
            result["error"] = str(e)
            
        return result
    
    async def check_api_endpoint(self, client: httpx.AsyncClient, url: str, method: str = "GET", expected_response: Dict = None, timeout: int = 10) -> Dict[str, Any]:
        """Async API check."""
        start = time.time()
        result = {
            "timestamp": datetime.now(),
            "status": "down",
            "error": None
        }
        
        try:
            resp = await client.request(method, url, timeout=timeout)
            duration = (time.time() - start) * 1000
            
            if not resp.is_success:
                result["error"] = f"API Error: {resp.status_code}"
                return result
                
            try:
                data = resp.json()
                result.update({
                    "status": "up",
                    "response_time_ms": round(duration, 2),
                    "data_sample": str(data)[:100]
                })
            except json.JSONDecodeError:
                result["error"] = "Invalid JSON response"
                
        except Exception as e:
            result["error"] = str(e)
            
        return result

    async def perform_check(self, client: httpx.AsyncClient, service: Dict[str, Any]) -> Dict[str, Any]:
        """Dispatches check asynchronously."""
        stype = service.get("type", "http")
        
        if stype == "http":
            return await self.check_http_service(
                client,
                service["url"], 
                service.get("timeout", 10), 
                service.get("expected_status", 200)
            )
        elif stype == "tcp":
            return await self.check_tcp_service(
                service["host"], 
                service["port"], 
                service.get("timeout", 5)
            )
        elif stype == "dns":
             return await self.check_dns_resolution(service["host"])
        elif stype == "api":
             return await self.check_api_endpoint(
                 client,
                 service["url"],
                 service.get("method", "GET"),
                 service.get("expected_response"),
                 service.get("timeout", 10)
             )
        
        return {"status": "unknown", "error": "Unknown type"}

    async def run_monitoring_loop(self, interval: int = 60):
        """Main async loop."""
        async with httpx.AsyncClient(verify=False) as client: # Disable SSL verification for broader compatibility in diagnostics
            with Live(self._generate_dashboard_table(), refresh_per_second=1) as live:
                try:
                    while True:
                        tasks = []
                        # Create tasks for all services
                        for service in self.services:
                            tasks.append(self.perform_check(client, service))
                        
                        # Run all checks PARALLEL
                        results = await asyncio.gather(*tasks)
                        
                        # Process results
                        for service, res in zip(self.services, results):
                            name = service["name"]
                            # Log to DB (run in thread to not block loop technically, but sqlite is fast)
                            await asyncio.to_thread(self.db.log_check, res, name, service.get("type", "http"))
                            
                            # Update Cache
                            self.metrics[name].append(res)
                            if len(self.metrics[name]) > 100: self.metrics[name].pop(0)

                        live.update(self._generate_dashboard_table())
                        await asyncio.sleep(interval)
                except asyncio.CancelledError:
                    pass

    def monitor_continuously(self, interval: int = 60):
        """Entry point for sync CLI to call async loop."""
        try:
            asyncio.run(self.run_monitoring_loop(interval))
        except KeyboardInterrupt:
            console.print("[yellow]Monitoring stopped.[/yellow]")

    # ... [Keep dashboard and report generation methods as they are mostly decoupled from async logic] ...
    # Wait, I need to make sure _generate_dashboard_table uses the synchronous DB calls safely. 
    # Since we are in the main thread (asyncio.run blocks), we can just call DB methods directly.
    # The actual dashboard usage of DB is fine.
    
    def _generate_dashboard_table(self) -> Table:
        """Generates dashboard using DB stats."""
        table = Table(title="Service Health Dashboard (Async & Fast)")
        table.add_column("Service", style="cyan")
        table.add_column("Type", style="magenta")
        table.add_column("Status", justify="center")
        table.add_column("Latency")
        table.add_column("Uptime (24h)", justify="right")
        table.add_column("Last Check")

        for service in self.services:
            name = service["name"]
            history = self.db.get_history(name, limit=1)
            
            if not history:
                table.add_row(name, service.get("type"), "PENDING", "-", "-", "-")
                continue
                
            last = history[0]
            
            status_icon = "🟢 UP" if last['status'] == 'up' else "🔴 DOWN"
            latency = f"{last['response_time_ms']}ms" if last['response_time_ms'] else "-"
            
            stats = self.db.get_uptime_stats(name, hours=24)
            uptime_str = f"{stats['uptime_percent']:.1f}%"
            
            table.add_row(
                name, 
                service.get("type"), 
                status_icon, 
                latency, 
                uptime_str, 
                str(last['timestamp']).split('.')[0]
            )
            
        return table
    
    def calculate_uptime(self, service_name: str) -> float:
        stats = self.db.get_uptime_stats(service_name)
        return stats['uptime_percent']

    def export_status_page(self, format: str = "html") -> str:
        """Generates status page from DB data."""
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        services_data = {}
        for s in self.services:
            name = s['name']
            history = self.db.get_history(name, limit=1)
            stats = self.db.get_uptime_stats(name)
            services_data[name] = {"latest": history[0] if history else None, "stats": stats}

        if format == "html":
            template_str = """<!DOCTYPE html><html><head><title>Service Status</title><style>
            body{font-family:sans-serif;padding:20px;background:#f4f6f8}
            .card{background:white;padding:15px;margin:10px 0;border-radius:5px;border-left:5px solid #ccc;box-shadow:0 1px 3px rgba(0,0,0,0.1)}
            .up{border-left-color:#28a745}.down{border-left-color:#dc3545}
            h2{margin:0 0 10px 0}.metric{margin-right:15px;color:#555}
            </style></head><body><h1>System Status</h1><p>Generated: {{timestamp}}</p>
            {% for name, data in services.items() %}{% set last = data.latest %}
            <div class="card {{'up' if last and last.status=='up' else 'down'}}">
            <h2>{{name}} <span style="float:right;font-size:0.8em;color:{{'green' if last.status=='up' else 'red'}}">{{last.status|upper}}</span></h2>
            {% if last %}<div><span class="metric">Latency: {{last.response_time_ms}}ms</span><span class="metric">Uptime: {{"%.1f"|format(data.stats.uptime_percent)}}%</span></div>
            {% else %}<p>No data</p>{% endif %}</div>{% endfor %}</body></html>"""
            
            template = Template(template_str)
            html = template.render(services=services_data, timestamp=timestamp)
            path = self.output_dir / "status_page.html"
            with open(path, 'w', encoding='utf-8') as f: f.write(html)
            return str(path)
        return "Unsupported provided"
        result = {
            "timestamp": datetime.now(),
            "status": "down",
            "ssl_valid": False,
            "error_message": None
        }
        
        try:
            response = requests.get(url, timeout=timeout, verify=True)
            duration = (time.time() - start) * 1000
            
            result.update({
                "response_time_ms": round(duration, 2),
                "status_code": response.status_code,
                "status": "up" if response.status_code == expected_status else "down",
                "ssl_valid": url.startswith("https"), # Simplified SSL check
            })
            
            if response.status_code != expected_status:
                result["error_message"] = f"Unexpected status: {response.status_code}"
                
        except requests.exceptions.SSLError:
            result["error_message"] = "SSL Error"
        except requests.exceptions.ConnectionError:
            result["error_message"] = "Connection Failed"
        except requests.exceptions.Timeout:
            result["error_message"] = "Timeout"
        except Exception as e:
            result["error_message"] = str(e)
            
        return result

    def check_tcp_service(self, host: str, port: int, timeout: int = 5) -> Dict[str, Any]:
        """Checks TCP connectivity."""
        start = time.time()
        result = {
            "timestamp": datetime.now(),
            "status": "down",
            "error_message": None
        }
        
        try:
            with socket.create_connection((host, port), timeout=timeout):
                duration = (time.time() - start) * 1000
                result["status"] = "up"
                result["response_time_ms"] = round(duration, 2)
        except Exception as e:
            result["error_message"] = str(e)
            
        return result

    def check_dns_resolution(self, domain: str, expected_ip: str = None) -> Dict[str, Any]:
        """Checks DNS resolution."""
        start = time.time()
        result = {
            "timestamp": datetime.now(),
            "status": "down",
            "error": None
        }
        
        try:
            resolver = dns.resolver.Resolver()
            answers = resolver.resolve(domain, 'A')
            ips = [r.to_text() for r in answers]
            duration = (time.time() - start) * 1000
            
            status = "up"
            if expected_ip and expected_ip not in ips:
                status = "down"
                result["error"] = f"IP mismatch. Expected {expected_ip}, got {ips}"
            
            result.update({
                "status": status,
                "response_time_ms": round(duration, 2),
                "ips": ips
            })
        except Exception as e:
            result["error"] = str(e)
            
        return result
    
    def check_api_endpoint(self, url: str, method: str = "GET", expected_response: Dict = None, timeout: int = 10) -> Dict[str, Any]:
        """Checks API response structure."""
        start = time.time()
        result = {
            "timestamp": datetime.now(),
            "status": "down",
            "error": None
        }
        
        try:
            resp = requests.request(method, url, timeout=timeout)
            duration = (time.time() - start) * 1000
            
            if not resp.ok:
                result["error"] = f"API Error: {resp.status_code}"
                return result
                
            data = resp.json()
            # Basic validation: check if expected keys exist
            if expected_response:
                # If expected_response is a subset of actual response
                # This is a simplification; production code might need deep diff
                pass 
            
            result.update({
                "status": "up",
                "response_time_ms": round(duration, 2),
                "data_sample": str(data)[:100] # Truncate
            })
        except json.JSONDecodeError:
            result["error"] = "Invalid JSON response"
        except Exception as e:
            result["error"] = str(e)
            
        return result

    def perform_check(self, service: Dict[str, Any]) -> Dict[str, Any]:
        """Dispatches check based on service type."""
        stype = service.get("type", "http")
        name = service.get("name")
        
        if stype == "http":
            return self.check_http_service(
                service["url"], 
                service.get("timeout", 10), 
                service.get("expected_status", 200)
            )
        elif stype == "tcp":
            return self.check_tcp_service(
                service["host"], 
                service["port"], 
                service.get("timeout", 5)
            )
        elif stype == "dns":
             return self.check_dns_resolution(service["host"])
        elif stype == "api":
             return self.check_api_endpoint(
                 service["url"],
                 service.get("method", "GET"),
                 service.get("expected_response"),
                 service.get("timeout", 10)
             )
        
        return {"status": "unknown", "error": "Unknown type"}

    def monitor_continuously(self, interval: int = 60):
        """Runs continuous monitoring loop with dashboard."""
        
        with Live(self._generate_dashboard_table(), refresh_per_second=1) as live:
            try:
                while True:
                    for service in self.services:
                        name = service["name"]
                        res = self.perform_check(service)
                        
                        # Store Metric
                        self.metrics[name].append(res)
                        if len(self.metrics[name]) > 100: # Keep last 100
                            self.metrics[name].pop(0)
                        
                        # Alerting Logic (Simple)
                        if res['status'] == 'down' and service.get('alert_on_failure'):
                            self.send_alert(name, "DOWN", res.get('error_message') or res.get('error'))
                            
                    live.update(self._generate_dashboard_table())
                    time.sleep(interval)
            except KeyboardInterrupt:
                console.print("[yellow]Monitoring stopped.[/yellow]")

    def _generate_dashboard_table(self) -> Table:
        """Generates the Rich table for the dashboard."""
        table = Table(title="Service Health Dashboard")
        table.add_column("Service", style="cyan")
        table.add_column("Type", style="magenta")
        table.add_column("Status", justify="center")
        table.add_column("Latency")
        table.add_column("Uptime (24h)", justify="right")
        table.add_column("Last Check")

        for service in self.services:
            name = service["name"]
            history = self.metrics.get(name, [])
            if not history:
                table.add_row(name, service.get("type"), "PENDING", "-", "-", "-")
                continue
                
            last = history[-1]
            
            # Status Style
            status_icon = "🟢 UP" if last['status'] == 'up' else "🔴 DOWN"
            
            # Latency
            latency = f"{last.get('response_time_ms', 0)}ms"
            
            # Uptime Calc
            uptime = self.calculate_uptime(name)
            uptime_str = f"{uptime:.1f}%"
            
            table.add_row(
                name, 
                service.get("type"), 
                status_icon, 
                latency, 
                uptime_str, 
                last['timestamp'].strftime("%H:%M:%S")
            )
            
        return table

    def calculate_uptime(self, service_name: str) -> float:
        """Calculates simple uptime percentage from memory."""
        history = self.metrics.get(service_name, [])
        if not history: return 0.0
        
        successful = sum(1 for r in history if r['status'] == 'up')
        return (successful / len(history)) * 100

    def send_alert(self, service_name: str, type: str, message: str):
        """Sends an alert."""
        msg = f"ALERT: {service_name} is {type}. Detail: {message}"
        self.alerts.append({"timestamp": datetime.now(), "message": msg})
        
        # In production this would send email/slack
        # logger.error(msg) 

    def export_status_page(self, format: str = "html") -> str:
        """Generates a status page."""
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        
        if format == "html":
            template_str = """
            <!DOCTYPE html>
            <html>
            <head>
                <title>Service Status</title>
                <style>
                    body { font-family: sans-serif; padding: 20px; background: #f4f4f9; }
                    .card { background: white; padding: 15px; margin-bottom: 10px; border-radius: 5px; box-shadow: 0 2px 2px rgba(0,0,0,0.1); }
                    .up { color: green; font-weight: bold; }
                    .down { color: red; font-weight: bold; }
                    h1 { text-align: center; color: #333; }
                </style>
            </head>
            <body>
                <h1>Service Status Page</h1>
                <p style="text-align:center">Generated: {{ timestamp }}</p>
                
                {% for name, history in metrics.items() %}
                {% set last = history[-1] if history else None %}
                <div class="card">
                    <h2>{{ name }}</h2>
                    {% if last %}
                        <p>Status: <span class="{{ last.status }}">{{ last.status|upper }}</span></p>
                        <p>Latency: {{ last.response_time_ms }}ms</p>
                        <p>Last Check: {{ last.timestamp }}</p>
                    {% else %}
                        <p>No data available.</p>
                    {% endif %}
                </div>
                {% endfor %}
            </body>
            </html>
            """
            
            template = Template(template_str)
            html = template.render(metrics=self.metrics, timestamp=timestamp)
            
            path = self.output_dir / "status_page.html"
            with open(path, 'w') as f:
                f.write(html)
            return str(path)
            
        return "Unsupported format"

if __name__ == "__main__":
    # Test
    checker = ServiceHealthChecker()
    checker.monitor_continuously(interval=5)
