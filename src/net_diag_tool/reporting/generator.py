import json
from pathlib import Path
from datetime import datetime
from typing import Dict, Any
from net_diag_tool.core.logger import setup_logger
from net_diag_tool.config.settings import get_settings

logger = setup_logger(__name__)
settings = get_settings()

class ReportGenerator:
    def __init__(self):
        self.output_dir = Path(settings.REPORT_OUTPUT_DIR)
        self.output_dir.mkdir(exist_ok=True)

    def generate_json_report(self, data: Dict[str, Any], filename: str = None):
        """Generates a JSON report of the diagnostic session."""
        if not filename:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"diagnostic_report_{timestamp}.json"
        
        filepath = self.output_dir / filename
        try:
            with open(filepath, 'w') as f:
                json.dump(data, f, indent=4, default=str)
            logger.info(f"Report generated at {filepath}")
            return filepath
        except Exception as e:
            logger.error(f"Failed to generate report: {e}")
            raise
