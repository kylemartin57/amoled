#!/bin/bash
# Apply saved screen rotation on startup
# Reads from ~/.touchscreen_scheduler/config.json

CONFIG_FILE="$HOME/.touchscreen_scheduler/config.json"
DISPLAY_OUTPUT="DP-1"
TOUCH_DEVICE="WaveShare WaveShare"

# Rotation transformation matrices
declare -A MATRICES
MATRICES["normal"]="1 0 0 0 1 0 0 0 1"
MATRICES["left"]="0 -1 1 1 0 0 0 0 1"
MATRICES["right"]="0 1 0 -1 0 1 0 0 1"
MATRICES["inverted"]="-1 0 1 0 -1 1 0 0 1"

export DISPLAY="${DISPLAY:-:0}"

# Wait for display to be ready
sleep 2

# Read rotation from config
if [ -f "$CONFIG_FILE" ]; then
    ROTATION=$(python3 -c "import json; print(json.load(open('$CONFIG_FILE')).get('rotation', 'normal'))" 2>/dev/null)
else
    ROTATION="normal"
fi

# Validate rotation
if [[ ! -v "MATRICES[$ROTATION]" ]]; then
    ROTATION="normal"
fi

echo "$(date): Applying rotation: $ROTATION" >> /tmp/screen-rotation.log

# Apply rotation
xrandr --output "$DISPLAY_OUTPUT" --rotate "$ROTATION" 2>> /tmp/screen-rotation.log
xinput set-prop "$TOUCH_DEVICE" "Coordinate Transformation Matrix" ${MATRICES[$ROTATION]} 2>> /tmp/screen-rotation.log

echo "$(date): Rotation applied successfully" >> /tmp/screen-rotation.log

