#!/bin/bash

# Exit in case of error
set -e

# Build and run containers
docker-compose -f docker-compose.yml up --build

# Hack to wait for postgres container to be up before running alembic migrations
sleep 7;

# Create migrations
#docker-compose run --rm guess-who alembic revision --autogenerate

# Run migrations
docker-compose run --rm guess-who alembic upgrade head

# Create initial data
docker-compose run --rm guess-who python3 app/initial_data.py