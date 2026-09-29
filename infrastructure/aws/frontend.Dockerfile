FROM node:22-alpine AS build
WORKDIR /app
COPY frontend/package*.json ./
RUN npm ci
COPY frontend/ ./
ENV VITE_MONITOR_ONLY=true
RUN npm run build
FROM caddy:2-alpine
COPY --from=build /app/dist /srv
COPY infrastructure/aws/Caddyfile /etc/caddy/Caddyfile
