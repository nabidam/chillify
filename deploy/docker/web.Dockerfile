# Chillify web image: the built SPA served by nginx, which also proxies /api
# and /media same-origin so the browser never makes a cross-origin request.

FROM node:24.18.0-trixie-slim AS build

WORKDIR /build

# npm ci installs exactly the committed lockfile; a lock drift fails the build.
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci --no-audit --no-fund

COPY frontend/ ./
RUN npm run build

FROM nginx:1.30.4 AS runtime

RUN rm -rf /usr/share/nginx/html/* /etc/nginx/conf.d/default.conf

COPY --from=build /build/dist /usr/share/nginx/html
COPY deploy/nginx.conf /etc/nginx/nginx.conf

RUN chmod -R a+rX /usr/share/nginx/html

EXPOSE 8080

CMD ["nginx", "-g", "daemon off;"]
