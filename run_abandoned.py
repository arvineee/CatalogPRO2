"""
PythonAnywhere Scheduled Task — run every hour
Schedule: python /home/CatalogPRO/CatalogPRO2/run_abandoned.py
"""
import sys, os
sys.path.insert(0, os.path.dirname(__file__))

from app import app
from scheduler import check_abandoned

if __name__ == "__main__":
    check_abandoned(app)

