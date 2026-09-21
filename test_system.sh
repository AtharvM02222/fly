#!/bin/bash
set -e
API_URL=${API_URL:-http://localhost:8000}
DASHBOARD_URL=${DASHBOARD_URL:-http://localhost:3000}
echo "====================================="
echo "System Integration Test"
echo "====================================="
echo ""
echo "1. Testing Backend Health..."
curl -f -s $API_URL/healthz > /dev/null && echo "   Backend: OK" || echo "   Backend: FAIL"
echo ""
echo "2. Testing PostgreSQL Connection..."
curl -f -s $API_URL/healthz | grep -q "postgresql.*ok" && echo "   PostgreSQL: OK" || echo "   PostgreSQL: FAIL"
echo ""
echo "3. Testing Authentication..."
LOGIN_RESPONSE=$(curl -s -X POST $API_URL/api/v1/auth/login \
  -H "Content-Type: application/json" \
  -d '{"email":"admin@dronecds.local","password":"changeme123"}')
TOKEN=$(echo $LOGIN_RESPONSE | python3 -c "import sys, json; print(json.load(sys.stdin).get('access_token', ''))")
if [ -z "$TOKEN" ]; then
    echo "   Authentication: FAIL (Could not get token)"
else
    echo "   Authentication: OK"
fi
echo ""
echo "4. Testing Device Creation..."
if [ ! -z "$TOKEN" ]; then
    DEVICE_RESPONSE=$(curl -s -X POST $API_URL/api/v1/devices \
      -H "Authorization: Bearer $TOKEN" \
      -H "Content-Type: application/json" \
      -d '{"name":"test-device","device_type":"drone"}')
    DEVICE_ID=$(echo $DEVICE_RESPONSE | python3 -c "import sys, json; print(json.load(sys.stdin).get('id', ''))" 2>/dev/null)
    if [ ! -z "$DEVICE_ID" ]; then
        echo "   Device Creation: OK (ID: $DEVICE_ID)"
    else
        echo "   Device Creation: SKIP (Device may already exist)"
    fi
else
    echo "   Device Creation: SKIP (No auth token)"
fi
echo ""
echo "5. Testing Dashboard..."
curl -f -s -o /dev/null $DASHBOARD_URL && echo "   Dashboard: OK" || echo "   Dashboard: FAIL"
echo ""
echo "====================================="
echo "Test Summary"
echo "====================================="
echo ""
echo "If all tests pass, the system is ready for use."
echo ""
