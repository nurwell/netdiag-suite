import sqlite3
from pathlib import Path
from datetime import datetime
from typing import List, Dict, Any, Optional

class DatabaseManager:
    def __init__(self, db_path: str = "netdiag.db"):
        self.db_path = db_path
        self._init_db()

    def _get_connection(self):
        return sqlite3.connect(self.db_path, check_same_thread=False)

    def _init_db(self):
        conn = self._get_connection()
        cursor = conn.cursor()
        
        # Service Checks Table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS service_checks (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                service_name TEXT NOT NULL,
                service_type TEXT NOT NULL,
                status TEXT NOT NULL,
                response_time_ms REAL,
                status_code INTEGER,
                error_message TEXT,
                timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        
        # Incidents Table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS incidents (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                service_name TEXT NOT NULL,
                issue_type TEXT NOT NULL,
                description TEXT,
                start_time DATETIME NOT NULL,
                end_time DATETIME,
                resolved BOOLEAN DEFAULT 0
            )
        ''')
        
        conn.commit()
        conn.close()

    def log_check(self, result: Dict[str, Any], service_name: str, service_type: str):
        """Logs a single service check result."""
        conn = self._get_connection()
        try:
            conn.execute('''
                INSERT INTO service_checks 
                (service_name, service_type, status, response_time_ms, status_code, error_message, timestamp)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            ''', (
                service_name,
                service_type,
                result.get('status'),
                result.get('response_time_ms'),
                result.get('status_code'),
                result.get('error_message') or result.get('error'),
                result.get('timestamp')
            ))
            conn.commit()
        finally:
            conn.close()

    def get_history(self, service_name: str, limit: int = 100) -> List[Dict[str, Any]]:
        """Retrieves check history for a service."""
        conn = self._get_connection()
        conn.row_factory = sqlite3.Row
        cursor = conn.execute('''
            SELECT * FROM service_checks 
            WHERE service_name = ? 
            ORDER BY timestamp DESC 
            LIMIT ?
        ''', (service_name, limit))
        
        rows = cursor.fetchall()
        conn.close()
        return [dict(row) for row in rows]

    def get_uptime_stats(self, service_name: str, hours: int = 24) -> Dict[str, Any]:
        """Calculates uptime percentage from DB."""
        conn = self._get_connection()
        cursor = conn.execute('''
            SELECT 
                COUNT(*) as total,
                SUM(CASE WHEN status = 'up' THEN 1 ELSE 0 END) as success,
                AVG(response_time_ms) as avg_latency
            FROM service_checks 
            WHERE service_name = ? 
            AND timestamp >= datetime('now', ?)
        ''', (service_name, f'-{hours} hours'))
        
        row = cursor.fetchone()
        conn.close()
        
        total = row[0] or 0
        success = row[1] or 0
        avg_latency = row[2] or 0
        
        return {
            "uptime_percent": (success / total * 100) if total > 0 else 0.0,
            "total_checks": total,
            "avg_latency": round(avg_latency, 2)
        }
