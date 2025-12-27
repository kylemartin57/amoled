#!/bin/bash
# Rotate screen and touch input for Waveshare display on Jetson
# Usage: ./rotate-screen.sh [normal|left|right|inverted]

DISPLAY_OUTPUT="DP-1"
TOUCH_DEVICE="WaveShare WaveShare"

# Rotation transformation matrices for touch input
declare -A MATRICES
MATRICES["normal"]="1 0 0 0 1 0 0 0 1"
MATRICES["left"]="0 -1 1 1 0 0 0 0 1"      # 90° CCW
MATRICES["right"]="0 1 0 -1 0 1 0 0 1"     # 90° CW  
MATRICES["inverted"]="-1 0 1 0 -1 1 0 0 1" # 180°

ROTATION="${1:-normal}"

if [[ ! -v "MATRICES[$ROTATION]" ]]; then
    echo "Usage: $0 [normal|left|right|inverted]"
    echo "  normal   - Portrait (default orientation)"
    echo "  left     - Landscape (90° counter-clockwise)"
    echo "  right    - Landscape (90° clockwise)"
    echo "  inverted - Portrait upside down (180°)"
    exit 1
fi

export DISPLAY="${DISPLAY:-:0}"

echo "Rotating display to: $ROTATION"

# Rotate the display
xrandr --output "$DISPLAY_OUTPUT" --rotate "$ROTATION"
if [ $? -ne 0 ]; then
    echo "Failed to rotate display. Check DISPLAY_OUTPUT variable."
    exit 1
fi

# Apply touch transformation
xinput set-prop "$TOUCH_DEVICE" "Coordinate Transformation Matrix" ${MATRICES[$ROTATION]}
if [ $? -ne 0 ]; then
    echo "Failed to set touch matrix. Check TOUCH_DEVICE variable."
    exit 1
fi

echo "Rotation applied successfully!"
echo "Display: $DISPLAY_OUTPUT"
echo "Touch: $TOUCH_DEVICE"

