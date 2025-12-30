# Stage 1: Build React Frontend
FROM node:20-alpine AS build-frontend
WORKDIR /app/configurator
COPY *.* ./
RUN npm install
RUN npm run build

# Stage 2: Final Image
FROM python:3.11-alpine
WORKDIR /app

# Install dependencies
RUN apk add --no-cache g++ gcc musl-dev python3-dev \
    && pip3 install --no-cache-dir flask flask-cors requests pyyaml gunicorn

# Copy built frontend
COPY --from=build-frontend /app/configurator/dist /app/dist

# Copy Python backend and scripts
COPY generate_tiles_api.py /app/configurator/
COPY server.py /app/

# Copy ESPHome files (needed for schema and scripts)
# COPY ../esphome/* /app/esphome

# Expose port for Ingress
EXPOSE 8099

# Start the server
CMD ["gunicorn", "-w", "4", "-b", "0.0.0.0:8099", "server:app"]
