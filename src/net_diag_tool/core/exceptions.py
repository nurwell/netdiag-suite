class NetDiagError(Exception):
    """Base exception for NetDiag Tool"""
    pass

class ConfigurationError(NetDiagError):
    """Raised when there is a configuration issue"""
    pass

class NetworkError(NetDiagError):
    """Raised when a network operation fails"""
    pass

class reportGenerationError(NetDiagError):
    """Raised when report generation fails"""
    pass
