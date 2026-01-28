from net_diag_tool.modules.services.checker import ServiceHealthChecker
from unittest.mock import patch, MagicMock

@patch('requests.get')
def test_check_http_service(mock_get):
    checker = ServiceHealthChecker()
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_get.return_value = mock_resp
    
    res = checker.check_http_service("https://google.com")
    assert res['status'] == 'up'
    assert res['status_code'] == 200

@patch('socket.create_connection')
def test_check_tcp_service(mock_socket):
    checker = ServiceHealthChecker()
    # No exception means success
    res = checker.check_tcp_service("localhost", 22)
    assert res['status'] == 'up'

@patch('dns.resolver.Resolver.resolve')
def test_check_dns(mock_resolve):
    checker = ServiceHealthChecker()
    mock_answer = MagicMock()
    mock_answer.to_text.return_value = "1.2.3.4"
    mock_resolve.return_value = [mock_answer]
    
    res = checker.check_dns_resolution("example.com", expected_ip="1.2.3.4")
    assert res['status'] == 'up'
    
    res_fail = checker.check_dns_resolution("example.com", expected_ip="9.9.9.9")
    assert res_fail['status'] == 'down'
    assert "IP mismatch" in res_fail['error']
