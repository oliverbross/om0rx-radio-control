#!/bin/bash

# FlexRadio Web Control v2.0 - Startup Script (Linux)
# This script starts both the FastAPI backend and SDC bridge server

APP_ENV="${APP_ENV:-local}"
BACKEND_HOST="${BACKEND_HOST:-127.0.0.1}"
BACKEND_PORT="${BACKEND_PORT:-8080}"

if [ "$APP_ENV" != "local" ] && [ "$APP_ENV" != "development" ]; then
    echo "APP_ENV must be 'local' or 'development'. Current value: $APP_ENV"
    exit 1
fi

ENABLE_RELOAD="false"
if [ "$APP_ENV" = "development" ] || [ "$UVICORN_RELOAD" = "1" ] || [ "$UVICORN_RELOAD" = "true" ] || [ "$UVICORN_RELOAD" = "yes" ] || [ "$UVICORN_RELOAD" = "on" ]; then
    ENABLE_RELOAD="true"
fi

BACKEND_PROBE_HOST="$BACKEND_HOST"
if [ "$BACKEND_HOST" = "0.0.0.0" ]; then
    BACKEND_PROBE_HOST="127.0.0.1"
fi
BACKEND_URL="http://${BACKEND_PROBE_HOST}:${BACKEND_PORT}"

echo ""
echo "========================================"
echo "   FlexRadio Web Control v2.0"
echo "   Complete Professional Interface"
echo "========================================"
echo ""
echo "Mode: $APP_ENV | Backend: $BACKEND_URL | Reload: $ENABLE_RELOAD"
echo ""

# Get project root from scripts/start/
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
PROJECT_ROOT="$( cd "$SCRIPT_DIR/../.." && pwd )"

# Check for Node.js
echo "🔍 Checking Node.js installation..."
if ! command -v node &> /dev/null; then
    echo ""
    echo "❌ ERROR: Node.js is not installed"
    echo ""
    echo "Please install Node.js from: https://nodejs.org/"
    echo "Or use your package manager:"
    echo "  Ubuntu/Debian: sudo apt install nodejs npm"
    echo "  CentOS/RHEL:   sudo yum install nodejs npm"
    echo "  Fedora:        sudo dnf install nodejs npm"
    echo ""
    exit 1
fi
NODE_VERSION=$(node --version)
echo "✅ Node.js found: $NODE_VERSION"

# Check for npm
echo "🔍 Checking npm installation..."
if ! command -v npm &> /dev/null; then
    echo ""
    echo "❌ ERROR: npm is not installed"
    echo ""
    echo "Please install npm (usually comes with Node.js)"
    echo ""
    exit 1
fi
NPM_VERSION=$(npm --version)
echo "✅ npm found: $NPM_VERSION"

# Install npm dependencies if needed
echo "🔍 Checking npm dependencies..."
if [ ! -d "$PROJECT_ROOT/node_modules" ]; then
    echo "📦 Installing npm dependencies..."
    cd "$PROJECT_ROOT"
    npm install
    if [ $? -ne 0 ]; then
        echo ""
        echo "❌ ERROR: Failed to install npm dependencies"
        echo ""
        exit 1
    fi
fi
echo "✅ npm dependencies ready"

# Check for Python
echo "🔍 Checking Python installation..."
if ! command -v python3 &> /dev/null; then
    echo ""
    echo "❌ ERROR: Python 3 is not installed"
    echo ""
    echo "Please install Python 3 from: https://www.python.org/"
    echo "Or use your package manager:"
    echo "  Ubuntu/Debian: sudo apt install python3 python3-pip"
    echo "  CentOS/RHEL:   sudo yum install python3 python3-pip"
    echo "  Fedora:        sudo dnf install python3 python3-pip"
    echo ""
    exit 1
fi
PYTHON_VERSION=$(python3 --version)
echo "✅ Python found: $PYTHON_VERSION"

# Detect local IP address
echo "🔍 Detecting network configuration..."
LOCAL_IP=$(hostname -I | awk '{print $1}')

echo ""
echo "✅ READY TO START"
echo ""
echo "📡 Access URLs:"
echo "   Desktop:    $BACKEND_URL"
if [ -n "$LOCAL_IP" ] && [ "$BACKEND_HOST" = "0.0.0.0" ]; then
    echo "   Mobile:     http://${LOCAL_IP}:${BACKEND_PORT}"
fi
echo ""

echo "🎯 Features Available:"
echo "   ✅ All radio controls (bands, modes, filters)"
echo "   ✅ S-Meter visualization"
echo "   ✅ AGC + DSP controls (NB, NR, ANF, APF)"
echo "   ✅ RX2 / SPLIT operation"
echo "   ✅ DX Spots with click-to-tune"
echo "   ✅ Real-time WebSocket sync"
echo "   ✅ SDC Decoded CW ticker (in CW mode)"
echo "   ✅ WSJT-X Integration (FT8/FT4 auto-logging + auto-rotate)"
echo ""

# Start Multi-Protocol Bridge Server (SDC + WSJT-X) in background
echo "🚀 Starting Multi-Protocol Bridge Server (SDC + WSJT-X)..."
cd "$PROJECT_ROOT"

# Set environment variables for WSJT-X integration
export TCP_HOST="127.0.0.1"
export TCP_PORT="12166"
export WSJTX_UDP_PORT="2237"
export WSJTX_UDP_MULTICAST="224.0.0.1"
export WS_PORT="8091"
export WSJTX_COMMAND_PORT="8092"
export WSJTX_ENABLED="true"

node "$PROJECT_ROOT/bridge/sdc-bridge-server.js" > /tmp/bridge-server.log 2>&1 &
BRIDGE_PID=$!

# Give it a moment to start
sleep 2

# Check if process is still running
if kill -0 $BRIDGE_PID 2>/dev/null; then
    echo "✅ Multi-Protocol Bridge Server started (PID: $BRIDGE_PID)"
    echo "   SDC WebSocket: ws://localhost:8091"
    echo "   WSJT-X UDP: listening on port 2237"
    echo "   WSJT-X Command API: http://127.0.0.1:8092/wsjtx/command"
else
    echo "⚠️  Bridge Server may have failed to start"
    echo "   (This is optional - the app will still work without it)"
    echo "   Check /tmp/bridge-server.log for details"
fi

echo ""
echo "🚀 Starting FastAPI backend server..."
echo ""
echo "========================================"
echo ""

# Start the server
cd "$PROJECT_ROOT"
UVICORN_ARGS=(backend.main:app --host "$BACKEND_HOST" --port "$BACKEND_PORT")
if [ "$ENABLE_RELOAD" = "true" ]; then
    UVICORN_ARGS+=(--reload)
fi

python3 -m uvicorn "${UVICORN_ARGS[@]}"

# Cleanup: Kill the Bridge Server when Python server exits
echo ""
echo "Stopping Multi-Protocol Bridge Server (PID: $BRIDGE_PID)..."
kill $BRIDGE_PID 2>/dev/null
wait $BRIDGE_PID 2>/dev/null
echo "✅ Cleanup complete"
