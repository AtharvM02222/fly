#!/bin/bash
set -e
ENVIRONMENT=${1:-production}
echo "====================================="
echo "Deploying Drone-CDS to $ENVIRONMENT"
echo "====================================="
if [ "$ENVIRONMENT" = "production" ]; then
    COMPOSE_FILE="infra/docker-compose.prod.yml"
else
    COMPOSE_FILE="infra/docker-compose.yml"
fi
echo "Building Docker images..."
docker-compose -f $COMPOSE_FILE build
echo "Starting services..."
docker-compose -f $COMPOSE_FILE up -d
echo "Waiting for PostgreSQL..."
sleep 10
echo "Running database migrations..."
docker-compose -f $COMPOSE_FILE exec backend alembic upgrade head
echo "Creating admin user (if not exists)..."
docker-compose -f $COMPOSE_FILE exec backend python -m app.scripts.create_admin \
    --email admin@dronecds.local \
    --password "${ADMIN_PASSWORD:-changeme123}" || true
echo ""
echo "====================================="
echo "Deployment complete!"
echo "====================================="
echo ""
echo "Services:"
echo "  Backend API:  http://localhost:8000"
echo "  Dashboard:    http://localhost:3000"
echo "  PostgreSQL:   localhost:5432"
echo ""
echo "Health check:"
curl -s http://localhost:8000/healthz | python -m json.tool || echo "Backend not ready yet"
echo ""
