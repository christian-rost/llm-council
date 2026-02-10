#!/bin/bash
# XQT5AIs Public API - Test Script
# Usage: ./test_api.sh

BACKEND_URL="https://5ais-backend.xqtfive.com"
ADMIN_USER="christian.rost"

echo "=== XQT5AIs API Test ==="
echo ""

# Step 1: Admin Login
read -s -p "Admin-Passwort: " ADMIN_PW
echo ""
echo ""
echo "--- Step 1: Admin Login ---"

LOGIN_RESPONSE=$(curl -s -X POST "$BACKEND_URL/api/auth/login" \
  -H "Content-Type: application/json" \
  -d "{\"username\":\"$ADMIN_USER\",\"password\":\"$ADMIN_PW\"}")

JWT_TOKEN=$(echo "$LOGIN_RESPONSE" | python3 -c "import sys,json; print(json.load(sys.stdin)['access_token'])" 2>/dev/null)

if [ -z "$JWT_TOKEN" ]; then
  echo "Login fehlgeschlagen!"
  echo "$LOGIN_RESPONSE"
  exit 1
fi

echo "Login OK. Token: ${JWT_TOKEN:0:20}..."
echo ""

# Step 2: Create API Key
echo "--- Step 2: API Key erstellen ---"

KEY_RESPONSE=$(curl -s -X POST "$BACKEND_URL/api/admin/api-keys" \
  -H "Authorization: Bearer $JWT_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"name":"Test Key"}')

API_KEY=$(echo "$KEY_RESPONSE" | python3 -c "import sys,json; print(json.load(sys.stdin)['key'])" 2>/dev/null)

if [ -z "$API_KEY" ]; then
  echo "API Key Erstellung fehlgeschlagen!"
  echo "$KEY_RESPONSE"
  exit 1
fi

echo "API Key erstellt: ${API_KEY:0:16}..."
echo ""

# Step 3: List API Keys
echo "--- Step 3: API Keys auflisten ---"

curl -s -X GET "$BACKEND_URL/api/admin/api-keys" \
  -H "Authorization: Bearer $JWT_TOKEN" | python3 -m json.tool

echo ""

# Step 4: Council Request
echo "--- Step 4: Council-Anfrage (dauert 30-60s) ---"

curl -s -X POST "$BACKEND_URL/api/v1/council" \
  -H "X-API-Key: $API_KEY" \
  -H "Content-Type: application/json" \
  -d '{"question":"Was ist der Unterschied zwischen Machine Learning und Deep Learning? Antworte kurz."}' | python3 -m json.tool

echo ""

# Step 5: Test invalid key -> 401
echo "--- Step 5: Ungültiger Key -> 401 ---"

HTTP_CODE=$(curl -s -o /dev/null -w "%{http_code}" -X POST "$BACKEND_URL/api/v1/council" \
  -H "X-API-Key: xqt5-invalid" \
  -H "Content-Type: application/json" \
  -d '{"question":"Test"}')

echo "HTTP Status: $HTTP_CODE (erwartet: 401)"
echo ""

# Step 6: Test empty question -> 422
echo "--- Step 6: Leere Frage -> 422 ---"

HTTP_CODE=$(curl -s -o /dev/null -w "%{http_code}" -X POST "$BACKEND_URL/api/v1/council" \
  -H "X-API-Key: $API_KEY" \
  -H "Content-Type: application/json" \
  -d '{"question":""}')

echo "HTTP Status: $HTTP_CODE (erwartet: 422)"
echo ""

echo "=== Tests abgeschlossen ==="
