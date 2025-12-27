#!/bin/bash
# Launcher script for Touchscreen Scheduler

cd "$(dirname "$0")"

# Kill any existing instance
pkill -f "python3.*scheduler.py" 2>/dev/null
sleep 1

# Set display if not set
export DISPLAY=${DISPLAY:-:0}

# Enable touch scrolling
export QT_QUICK_BACKEND=software
export QT_QPA_PLATFORMTHEME=gtk3

# Run the scheduler
exec python3 scheduler.py "$@"
