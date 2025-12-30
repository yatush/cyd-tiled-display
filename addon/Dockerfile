# Stage 1: Build React Frontend
FROM node:20-alpine AS build-frontend
WORKDIR /app/configurator
COPY configurator/package*.json ./
RUN npm install
COPY configurator/ ./
RUN npm run build

# Stage 2: Final Image
FROM python:3.11-alpine
WORKDIR /app

# Install dependencies
RUN apk add --no-cache g++ gcc musl-dev python3-dev \
    && pip3 install --no-cache-dir flask flask-cors requests pyyaml

# Copy built frontend
COPY --from=build-frontend /app/configurator/dist /app/dist

# Copy Python backend and scripts
COPY configurator/generate_tiles_api.py /app/configurator/
COPY addon/server.py /app/server.py

# Copy ESPHome files (needed for schema and scripts)
COPY esphome /app/esphome

# Expose port for Ingress
EXPOSE 8099

# Start the server
CMD ["python3", "server.py"]
