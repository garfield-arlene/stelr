import sys
import os

# Ensure /app is always on the Python path so the plugins package is found
sys.path.insert(0, "/app")

bind = "0.0.0.0:5000"
workers = 2
preload_app = True
loglevel = "info"
