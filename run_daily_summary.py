"""
PythonAnywhere Scheduled Task — run daily at 08:00
Schedule: python /home/CatalogPRO/CatalogPRO2/run_daily_summary.py
"""
import sys, os
sys.path.insert(0, os.path.dirname(__file__))

from app import app
from scheduler import daily_summary

if __name__ == "__main__":
    daily_summary(app)

