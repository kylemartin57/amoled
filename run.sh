#!/bin/bash
cd "$(dirname "$0")"
export DISPLAY=${DISPLAY:-:0}
exec python3 quote_display.py "$@"
