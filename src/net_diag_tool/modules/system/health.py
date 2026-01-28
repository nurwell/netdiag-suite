import platform
import psutil
import json
import logging
import time
import socket
import smtplib
import subprocess
import threading
from email.mime.text import MIMEText
from pathlib import Path
from datetime import datetime
from typing import Dict, Any, List, Optional
from collections import deque

from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from rich.live import Live
from rich.layout import Layout
from rich.progress import Progress, BarColumn, TextColumn

from net_diag_tool.core.logger import setup_logger

logger = setup_logger(__name__)
console = Console()

class SystemHealthMonitor:
    """
    Enterprise-grade System Health Monitor.
    Monitors CPU, Memory, Disk, Network, and Critical Services.
    """

    def __init__(self, config_file: str = None):
        """
        Initialize with config file.
        """
        self.os_type = platform.system().lower()
        
        # Determine config path
        if config_file:
            self.config_path = Path(config_file)
        else:
            # Default to relative path from this file
            self.config_path = Path(__file__).parent.parent.parent / "config" / "monitoring.json"

        self.config = self._load_config()
        self.thresholds = self.config.get("thresholds", {})
        
        # Metrics history for anomaly detection (store last 100 points)
        self.history = {
            "cpu_percent": deque(maxlen=100),
            "memory_percent": deque(maxlen=100),
            "disk_io": deque(maxlen=100)
        }
        
        self.alerts = []

    def _load_config(self) -> Dict[str, Any]:
        """Loads configuration from JSON file."""
        defaults = {
            "thresholds": {
                "cpu_percent_critical": 90,
                "cpu_percent_warning": 80,
                "memory_percent_critical": 90,
                "memory_percent_warning": 85,
                "disk_percent_critical": 90,
                "disk_percent_warning": 85
            },
            "alerting": {"enabled": False},
            "critical_services": ["docker", "nginx", "ssh"]
        }
        
        if self.config_path.exists():
            try:
                with open(self.config_path, 'r') as f:
                    return json.load(f)
            except Exception as e:
                logger.error(f"Failed to load config from {self.config_path}: {e}")
                return defaults
        else:
            logger.warning(f"Config file not found at {self.config_path}. Using defaults.")
            return defaults

    def _get_status(self, value: float, metric_name: str) -> str:
        """Determines status based on thresholds."""
        crit = self.thresholds.get(f"{metric_name}_critical", 90)
        warn = self.thresholds.get(f"{metric_name}_warning", 80)
        
        if value >= crit:
            return "critical"
        elif value >= warn:
            return "warning"
        return "healthy"

    def get_cpu_metrics(self) -> Dict[str, Any]:
        """Collects detailed CPU metrics."""
        try:
            total_usage = psutil.cpu_percent(interval=0.5)
            per_core = psutil.cpu_percent(interval=0.1, percpu=True)
            freq = psutil.cpu_freq()
            
            # Load Avg (Unix only usually, but psutil emulates or returns None on Windows)
            load_avg = [0, 0, 0]
            if hasattr(psutil, "getloadavg"):
                 load_avg = psutil.getloadavg()

            # Top Processes
            top_processes = []
            for proc in psutil.process_iter(['pid', 'name', 'cpu_percent', 'exe']):
                try:
                    pinfo = proc.info
                    top_processes.append(pinfo)
                except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
                    pass
            
            # Sort by CPU usage and take top 5
            top_processes.sort(key=lambda x: x.get('cpu_percent', 0.0), reverse=True)
            top_processes = top_processes[:5]

            status = self._get_status(total_usage, "cpu_percent")
            
            self.history["cpu_percent"].append(total_usage)

            return {
                "total_usage": total_usage,
                "per_core": per_core,
                "frequency": {
                    "current": getattr(freq, 'current', 0),
                    "min": getattr(freq, 'min', 0),
                    "max": getattr(freq, 'max', 0)
                },
                "load_average": load_avg,
                "top_processes": top_processes,
                "status": status
            }
        except Exception as e:
            logger.error(f"Error getting CPU metrics: {e}")
            return {"error": str(e)}

    def get_memory_metrics(self) -> Dict[str, Any]:
        """Collects memory metrics."""
        try:
            mem = psutil.virtual_memory()
            swap = psutil.swap_memory()
            
            # Top Memory Processes
            top_processes = []
            for proc in psutil.process_iter(['pid', 'name', 'memory_percent', 'memory_info']):
                try:
                    pinfo = proc.info
                    pinfo['rss'] = pinfo['memory_info'].rss
                    del pinfo['memory_info'] # Cleanup object
                    top_processes.append(pinfo)
                except (psutil.NoSuchProcess, psutil.AccessDenied):
                    pass
            
            top_processes.sort(key=lambda x: x.get('memory_percent', 0.0), reverse=True)
            top_processes = top_processes[:5]
            
            # Detect leaks (basic heuristic)
            leaks = [p for p in top_processes if p['memory_percent'] > 50]
            
            status = self._get_status(mem.percent, "memory_percent")
            self.history["memory_percent"].append(mem.percent)

            return {
                "total_gb": round(mem.total / (1024**3), 2),
                "used_gb": round(mem.used / (1024**3), 2),
                "available_gb": round(mem.available / (1024**3), 2),
                "percent": mem.percent,
                "swap_percent": swap.percent,
                "top_processes": top_processes,
                "leaks_detected": leaks,
                "status": status
            }
        except Exception as e:
            logger.error(f"Error getting Memory metrics: {e}")
            return {"error": str(e)}

    def get_disk_metrics(self) -> List[Dict[str, Any]]:
        """Collects disk usage for all partitions."""
        disks = []
        try:
            parts = psutil.disk_partitions(all=False)
            usage_io = psutil.disk_io_counters()
            
            for part in parts:
                # Skip snap or loop devices often found on Linux
                if 'snap' in part.device or 'loop' in part.device:
                    continue
                
                try:
                    usage = psutil.disk_usage(part.mountpoint)
                    status = self._get_status(usage.percent, "disk_percent")
                    
                    disks.append({
                        "device": part.device,
                        "mountpoint": part.mountpoint,
                        "fstype": part.fstype,
                        "total_gb": round(usage.total / (1024**3), 2),
                        "used_gb": round(usage.used / (1024**3), 2),
                        "free_gb": round(usage.free / (1024**3), 2),
                        "percent": usage.percent,
                        "status": status
                    })
                except PermissionError:
                    continue

            # Record aggregated IO for anomaly detection (simplified)
            if usage_io:
                io_activity = usage_io.read_count + usage_io.write_count
                self.history["disk_io"].append(io_activity)

        except Exception as e:
            logger.error(f"Error getting Disk metrics: {e}")
            
        return disks

    def get_network_metrics(self) -> Dict[str, Any]:
        """Collects network IO and connectivity info."""
        try:
            net_io = psutil.net_io_counters()
            
            # Connectivity Check
            connected = False
            try:
                # Ping Google DNS (8.8.8.8) port 53 (DNS)
                socket.create_connection(("8.8.8.8", 53), timeout=3)
                connected = True
            except OSError:
                pass

            return {
                "bytes_sent_gb": round(net_io.bytes_sent / (1024**3), 2),
                "bytes_recv_gb": round(net_io.bytes_recv / (1024**3), 2),
                "packets_sent": net_io.packets_sent,
                "packets_recv": net_io.packets_recv,
                "errors_in": net_io.errin,
                "errors_out": net_io.errout,
                "internet_connected": connected
            }
        except Exception as e:
            logger.error(f"Error getting Network metrics: {e}")
            return {}

    def check_critical_services(self) -> List[Dict[str, Any]]:
        """Checks status of critical services."""
        services_to_check = self.config.get("critical_services", [])
        status_list = []
        
        # 1. Check via psutil for cross-platform process existence
        # This is often more reliable than querying systemd/service manager for simple checks
        running_procs = {p.name().lower() for p in psutil.process_iter(['name'])}
        
        for svc in services_to_check:
            # Basic match: checks if substring is in any running process name
            # Not perfect, but robust across Windows/Linux without os-specific calls
            is_running = any(svc.lower() in p_name for p_name in running_procs)
            
            # If not found via process list, try OS specific commands
            if not is_running:
                 if self.os_type == 'linux':
                     is_running = self._check_systemd_service(svc)
                 elif self.os_type == 'windows':
                     is_running = self._check_windows_service(svc)
                     
            status_list.append({
                "service": svc,
                "status": "Running" if is_running else "Stopped",
                "healthy": is_running
            })
            
        return status_list
    
    def _check_systemd_service(self, service_name: str) -> bool:
        """Checks systemd service status."""
        try:
            cmd = ["systemctl", "is-active", service_name]
            result = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
            return result.returncode == 0
        except FileNotFoundError:
            return False

    def _check_windows_service(self, service_name: str) -> bool:
        """Checks Windows service status via sc query."""
        try:
            # sc query return text that includes "STATE : 4 RUNNING" if running
            cmd = ["sc", "query", service_name]
            result = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
            return "RUNNING" in result.stdout
        except FileNotFoundError:
            return False

    def get_system_info(self) -> Dict[str, Any]:
        """Provides static system details."""
        try:
            boot_time = datetime.fromtimestamp(psutil.boot_time())
            uptime = datetime.now() - boot_time
            
            return {
                "hostname": socket.gethostname(),
                "os": platform.system(),
                "os_release": platform.release(),
                "os_version": platform.version(),
                "machine": platform.machine(),
                "processor": platform.processor(),
                "cpu_cores_physical": psutil.cpu_count(logical=False) or 1,
                "cpu_cores_logical": psutil.cpu_count(logical=True),
                "boot_time": boot_time.isoformat(),
                "uptime": str(uptime).split('.')[0],
                "python_version": platform.python_version()
            }
        except Exception as e:
            return {"error": str(e)}

    def check_system_logs_for_errors(self, lines_to_check: int = 200) -> Dict[str, Any]:
        """
        Scans system logs for recent errors.
        Linux: /var/log/syslog
        Windows: Powershell Get-EventLog
        """
        errors = []
        
        if self.os_type == 'linux':
             log_path = Path("/var/log/syslog")
             if log_path.exists():
                 try:
                     # Use 'tail' command for efficiency
                     cmd = ["tail", "-n", str(lines_to_check), str(log_path)]
                     result = subprocess.run(cmd, stdout=subprocess.PIPE, text=True)
                     for line in result.stdout.splitlines():
                         if "error" in line.lower() or "critical" in line.lower() or "fail" in line.lower():
                             errors.append(line.strip())
                 except Exception as e:
                     errors.append(f"Error reading syslog: {e}")
        
        elif self.os_type == 'windows':
            # Use PowerShell to get recent Error events from System log
            # This avoids heavy pywin32 dependency
            try:
                ps_script = f"Get-EventLog -LogName System -Newest {lines_to_check} -EntryType Error | Select-Object -ExpandProperty Message"
                cmd = ["powershell", "-Command", ps_script]
                result = subprocess.run(cmd, stdout=subprocess.PIPE, text=True)
                lines = result.stdout.splitlines()
                # Filter empty lines
                errors = [line.strip() for line in lines if line.strip()]
            except Exception as e:
                 errors.append(f"Error querying EventLog: {e}")
                 
        return {
            "error_count": len(errors),
            "recent_errors": errors[:5] # Return only last 5 distinct errors to not flood
        }

    def detect_anomalies(self) -> List[str]:
        """Checks history for sudden spikes."""
        anomalies = []
        
        # Check CPU Spike
        if len(self.history["cpu_percent"]) > 10:
            recent_avg = sum(list(self.history["cpu_percent"])[-5:]) / 5
            long_avg = sum(self.history["cpu_percent"]) / len(self.history["cpu_percent"])
            if recent_avg > (long_avg * 1.5) and recent_avg > 50:
                anomalies.append("CPU usage significantly higher than average")

        # Check Memory Trend
        if len(self.history["memory_percent"]) > 10:
             recent_mem = list(self.history["memory_percent"])[-1]
             start_mem = list(self.history["memory_percent"])[0]
             if recent_mem > (start_mem + 15): # 15% growth
                 anomalies.append("Memory usage detected increasing trend (Possible Leak)")
                 
        return anomalies

    def generate_health_report(self) -> Dict[str, Any]:
        """Aggregates all metrics into a report."""
        cpu = self.get_cpu_metrics()
        mem = self.get_memory_metrics()
        disks = self.get_disk_metrics()
        net = self.get_network_metrics()
        services = self.check_critical_services()
        logs = self.check_system_logs_for_errors()
        sys_info = self.get_system_info()
        anomalies = self.detect_anomalies()
        
        # Calculate Score (0-100)
        score = 100
        if cpu.get('status') == 'critical': score -= 20
        elif cpu.get('status') == 'warning': score -= 10
        
        if mem.get('status') == 'critical': score -= 20
        elif mem.get('status') == 'warning': score -= 10
        
        for d in disks:
            if d.get('status') == 'critical': score -= 10
            elif d.get('status') == 'warning': score -= 5
            
        if not net.get('internet_connected'): score -= 10
        
        failed_services = [s for s in services if not s['healthy']]
        score -= (len(failed_services) * 10)
        
        # Score floor
        score = max(0, score)
        
        report = {
            "timestamp": datetime.now().isoformat(),
            "health_score": score,
            "metrics": {
                "system": sys_info,
                "cpu": cpu,
                "memory": mem,
                "disk": disks,
                "network": net,
                "services": services,
                "logs": logs
            },
            "anomalies": anomalies,
            "recommendations": []
        }
        
        # Recommendations
        if score < 100:
            if cpu.get('status') == 'critical':
                report['recommendations'].append("High CPU Usage: Check top processes.")
            if mem.get('status') == 'critical':
                report['recommendations'].append("High Memory Usage: Potential leak or upgrade needed.")
            if len(failed_services) > 0:
                report['recommendations'].append(f"Restart failed services: {', '.join([s['service'] for s in failed_services])}")
            if disks and any(d['percent'] > 90 for d in disks):
                report['recommendations'].append("Free up disk space on critical partitions.")
                
        return report

    def send_alert_email(self, report: Dict[str, Any]):
        """Sends email alert if configured and needed."""
        alert_cfg = self.config.get("alerting", {})
        if not alert_cfg.get("enabled") or not alert_cfg.get("email_enabled"):
            return

        if report['health_score'] == 100:
            return # No alert needed
            
        try:
            logger.info("Sending alert email...")
            msg = MIMEText(json.dumps(report, indent=4))
            msg['Subject'] = f"ALERT: System Health Score {report['health_score']} on {socket.gethostname()}"
            msg['From'] = alert_cfg['sender_email']
            msg['To'] = alert_cfg['receiver_email']

            with smtplib.SMTP(alert_cfg['smtp_server'], alert_cfg['smtp_port']) as server:
                server.starttls()
                server.login(alert_cfg['smtp_user'], alert_cfg['smtp_password'])
                server.send_message(msg)
                
        except Exception as e:
            logger.error(f"Failed to send email alert: {e}")

    def dashboard(self):
        """Displays a real-time Live dashboard."""
        layout = Layout()
        layout.split_column(
            Layout(name="header", size=3),
            Layout(name="body"),
            Layout(name="footer", size=3)
        )
        layout["body"].split_row(
            Layout(name="left"),
            Layout(name="right")
        )
        
        with Live(layout, refresh_per_second=1, screen=True):
            try:
                while True:
                    report = self.generate_health_report()
                    
                    # Header
                    header = Panel(
                        f"System Health Monitor - {socket.gethostname()} | Score: {report['health_score']}/100 | {report['timestamp']}",
                        style=f"bold {'green' if report['health_score'] > 80 else 'red'}"
                    )
                    layout["header"].update(header)
                    
                    # Left Column: Metrics
                    cpu_table = Table(title="CPU & Memory")
                    cpu_table.add_column("Metric")
                    cpu_table.add_column("Value")
                    
                    c = report['metrics']['cpu']
                    m = report['metrics']['memory']
                    cpu_table.add_row("CPU Usage", f"{c['total_usage']}%")
                    cpu_table.add_row("Memory %", f"{m['percent']}%")
                    cpu_table.add_row("Disk Usage", f"{report['metrics']['disk'][0]['percent'] if report['metrics']['disk'] else 'N/A'}%")
                    
                    layout["left"].update(Panel(cpu_table))
                    
                    # Right Column: Services & Issues
                    svc_table = Table(title="Services")
                    svc_table.add_column("Name")
                    svc_table.add_column("Status")
                    
                    for s in report['metrics']['services']:
                        svc_table.add_row(s['service'], f"[green]{s['status']}[/green]" if s['healthy'] else f"[red]{s['status']}[/red]")
                        
                    layout["right"].update(Panel(svc_table))
                    
                    # Footer: Recommendations
                    recs = "\n".join(report['recommendations']) if report['recommendations'] else "No issues detected."
                    layout["footer"].update(Panel(f"Recommendations: {recs}", title="Alerts"))
                    
                    time.sleep(2)
            except KeyboardInterrupt:
                pass

if __name__ == "__main__":
    monitor = SystemHealthMonitor()
    monitor.dashboard()
