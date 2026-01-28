from net_diag_tool.modules.logs.analyzer import LogAnalyzer
from unittest.mock import patch, mock_open

def test_detect_log_format():
    # Test Apache
    with patch("builtins.open", mock_open(read_data='127.0.0.1 - - [28/Jan/2025:14:30:45 +0000] "GET / HTTP/1.1" 200 1024')):
        with patch("pathlib.Path.exists", return_value=True):
            analyzer = LogAnalyzer("test.log")
            assert analyzer.detect_log_format() == "apache"
    
    # Test Syslog
    with patch("builtins.open", mock_open(read_data='Jan 28 14:30:45 ubuntu sshd[1234]: Accepted password')):
        with patch("pathlib.Path.exists", return_value=True):
            analyzer = LogAnalyzer("test.log")
            assert analyzer.detect_log_format() == "syslog"

def test_parse_apache_line():
    line = '192.168.1.1 - - [28/Jan/2025:14:30:45 +0000] "GET /index.html HTTP/1.1" 200 512 "-" "Mozilla/5.0"'
    analyzer = LogAnalyzer("dummy")
    parsed = analyzer.parse_apache_log(line)
    
    assert parsed is not None
    assert parsed['ip'] == "192.168.1.1"
    assert parsed['status'] == 200
    assert parsed['bytes'] == 512
    assert parsed['method'] == "GET"
