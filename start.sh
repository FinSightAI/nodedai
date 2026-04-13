#!/bin/sh
# Replace __PORT__ placeholder with actual $PORT (Render sets this)
PORT=${PORT:-8080}
UVICORN_PORT=8000

sed "s/__PORT__/$PORT/g" /app/nginx.conf > /tmp/nginx.conf

# Start FastAPI/uvicorn in background
uvicorn server:app --host 127.0.0.1 --port $UVICORN_PORT --workers 1 &

# Wait for uvicorn to be ready
for i in $(seq 1 30); do
  curl -sf http://127.0.0.1:$UVICORN_PORT/health > /dev/null 2>&1 && break
  sleep 1
done

# Start nginx in foreground
exec nginx -c /tmp/nginx.conf -g "daemon off;"
