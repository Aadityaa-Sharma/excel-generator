"""
Gunicorn configuration for production deployment.
Optimized for Render free tier (512MB RAM, limited CPU).
"""
import os
import multiprocessing

# Server socket
bind = f"0.0.0.0:{os.environ.get('PORT', '5000')}"

# Worker processes
# Render free tier: use 2 workers max to stay within memory limits
workers = int(os.environ.get("WEB_CONCURRENCY", "2"))
worker_class = "sync"
threads = 2

# Timeout
timeout = 300  # 5 minutes for large document processing
graceful_timeout = 30
keepalive = 5

# Startup
preload_app = False  # Don't preload to keep memory low at startup

# Logging
accesslog = "-"
errorlog = "-"
loglevel = os.environ.get("LOG_LEVEL", "info").lower()

# Memory management (disabled max_requests to preserve in-memory job state)
# max_requests = 100
# max_requests_jitter = 20

# Worker recycling to prevent memory leaks
worker_tmp_dir = "/dev/shm"  # Use shared memory for faster worker heartbeat
