# syntax=docker/dockerfile:1
FROM node:24-alpine AS build
WORKDIR /app
ENV CI=1
COPY package.json package-lock.json ./
RUN npm ci
COPY . .
ARG VITE_BASE_URL=/
ENV VITE_BASE_URL=$VITE_BASE_URL
RUN npm run build

FROM nginx:1.30.4-alpine AS runtime
# SPA history fallback handled here; the host + compose gateway only proxy.
COPY deploy/nginx.conf /etc/nginx/conf.d/default.conf
COPY --from=build /app/dist /usr/share/nginx/html
EXPOSE 80
