#!/usr/bin/env bash
set -u

CONFIG_GLOB="/config/tuya_camera_bridge_*.json"
BRIDGE_PID=""

find_config() {
    ls -1t $CONFIG_GLOB 2>/dev/null | head -1
}

shutdown() {
    if [ -n "$BRIDGE_PID" ]; then
        kill "$BRIDGE_PID" 2>/dev/null || true
        wait "$BRIDGE_PID" 2>/dev/null || true
    fi
    exit 0
}
trap shutdown TERM INT

while true; do
    echo "Waiting for the Tuya Camera Bridge integration configuration..."
    while [ -z "$(find_config)" ]; do
        sleep 5
    done

    CONFIG_PATH=$(find_config)
    CONFIG_HASH=$(md5sum "$CONFIG_PATH" | cut -d' ' -f1)
    tuya-camera-bridge addon --config "$CONFIG_PATH" &
    BRIDGE_PID=$!

    RESTART_FOR_CONFIG=false
    while kill -0 "$BRIDGE_PID" 2>/dev/null; do
        sleep 10
        NEW_CONFIG=$(find_config)
        if [ "$NEW_CONFIG" != "$CONFIG_PATH" ]; then
            RESTART_FOR_CONFIG=true
            kill "$BRIDGE_PID" 2>/dev/null || true
            break
        fi
        NEW_HASH=$(md5sum "$CONFIG_PATH" 2>/dev/null | cut -d' ' -f1)
        if [ -n "$NEW_HASH" ] && [ "$NEW_HASH" != "$CONFIG_HASH" ]; then
            RESTART_FOR_CONFIG=true
            kill "$BRIDGE_PID" 2>/dev/null || true
            break
        fi
    done

    wait "$BRIDGE_PID" 2>/dev/null
    EXIT_CODE=$?
    BRIDGE_PID=""
    if [ "$RESTART_FOR_CONFIG" != true ]; then
        echo "Bridge exited with status $EXIT_CODE; restarting in 5 seconds"
        sleep 5
    fi
done
