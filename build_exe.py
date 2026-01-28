import PyInstaller.__main__
from pathlib import Path

HERE = Path(__file__).parent

def build():
    PyInstaller.__main__.run([
        'src/net_diag_tool/main.py',
        '--name=netdiag',
        '--onefile',
        '--clean',
        '--add-data=src/net_diag_tool/config;net_diag_tool/config', # Include default config
        '--hidden-import=netifaces',
        '--hidden-import=httpx',
        '--hidden-import=rich',
        '--hidden-import=typer',
        '--hidden-import=dns',
    ])

if __name__ == '__main__':
    build()
