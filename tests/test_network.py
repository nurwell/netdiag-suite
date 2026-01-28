from net_diag_tool.modules.network.diagnostics import NetworkDiagnostics
from unittest.mock import patch, MagicMock

@patch('subprocess.run')
def test_ping_host(mock_run):
    tool = NetworkDiagnostics()
    
    # Mock successful ping output (Linux style)
    mock_run.return_value.returncode = 0
    mock_run.return_value.stdout = "4 packets transmitted, 4 received, 0% packet loss, time 3000ms\nrtt min/avg/max/mdev = 10.0/12.5/15.0/2.2 ms"
    
    result = tool.ping_host("localhost")
    assert result['success'] is True
    assert result['packet_loss_percent'] == 0.0
    
    # Mock failed ping
    mock_run.return_value.returncode = 1
    mock_run.return_value.stdout = "100% packet loss"
    
    result = tool.ping_host("invalid-host")
    assert result['success'] is False

@patch('requests.get')
def test_check_http_status(mock_get):
    tool = NetworkDiagnostics()
    
    # Mock success
    start_time = 0
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.ok = True
    mock_response.reason = "OK"
    mock_response.history = []
    mock_response.headers = {}
    mock_get.return_value = mock_response
    
    result = tool.check_http_status("http://example.com")
    assert result['is_active'] is True
    assert result['status_code'] == 200

    # Mock connection error
    mock_get.side_effect = Exception("Connection Refused")
    result = tool.check_http_status("http://bad-url.com")
    assert result['is_active'] is False
