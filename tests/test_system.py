from net_diag_tool.modules.system.health import SystemHealthMonitor
from unittest.mock import patch, MagicMock

def test_system_health_monitor_init():
    monitor = SystemHealthMonitor()
    assert monitor.config is not None
    assert "cpu_percent" in monitor.history

@patch('psutil.cpu_percent')
def test_get_cpu_metrics(mock_cpu):
    monitor = SystemHealthMonitor()
    mock_cpu.return_value = 50.0
    
    metrics = monitor.get_cpu_metrics()
    assert metrics['total_usage'] == 50.0
    assert metrics['status'] == 'healthy'

@patch('psutil.virtual_memory')
def test_get_memory_metrics(mock_mem):
    monitor = SystemHealthMonitor()
    mock_mem_obj = MagicMock()
    mock_mem_obj.total = 16 * 1024**3
    mock_mem_obj.used = 8 * 1024**3
    mock_mem_obj.available = 8 * 1024**3
    mock_mem_obj.percent = 50.0
    mock_mem.return_value = mock_mem_obj
    
    metrics = monitor.get_memory_metrics()
    assert metrics['total_gb'] == 16.0
    assert metrics['percent'] == 50.0
    assert metrics['status'] == 'healthy'
