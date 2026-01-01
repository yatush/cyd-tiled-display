# Stage 1: Build React Frontend
FROM node:20-alpine AS build-frontend
WORKDIR /app
COPY configurator/package.json configurator/package-lock.json ./
RUN npm install
COPY configurator/ ./
RUN npm run build

# Stage 2: Final Image
FROM python:3.11-alpine
WORKDIR /app

# Install dependencies
RUN apk add --no-cache g++ gcc musl-dev python3-dev \
    && pip3 install --no-cache-dir flask flask-cors requests pyyaml gunicorn

# Copy built frontend
COPY --from=build-frontend /app/dist /app/configurator/dist

# Copy Python backend and scripts
COPY configurator/generate_tiles_api.py /app/configurator/
COPY configurator/server.py /app/configurator/

# Copy ESPHome files (needed for schema and scripts)
COPY esphome /app/esphome

# Expose port for Ingress
ENV PORT=8099
EXPOSE $PORT

# Start the server
CMD gunicorn -w 4 -b 0.0.0.0:$PORT --chdir /app/configurator server:app
