"""
PythonAnywhere Scheduled Task — run weekly on Sunday at 02:00
Schedule: python /home/CatalogPRO/CatalogPRO2/run_backup.py
"""
import sys, os
sys.path.insert(0, os.path.dirname(__file__))

from scheduler import run_backup

if __name__ == "__main__":
    run_backup()

