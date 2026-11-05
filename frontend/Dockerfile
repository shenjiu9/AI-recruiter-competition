FROM node:22-alpine AS build
WORKDIR /src
RUN npm install -g pnpm@10.28.0
COPY package.json pnpm-lock.yaml pnpm-workspace.yaml tsconfig.base.json turbo.json ./
COPY frontend ./frontend
RUN pnpm install --frozen-lockfile
ARG VITE_USE_MOCK=false
ENV VITE_USE_MOCK=${VITE_USE_MOCK}
RUN pnpm build

FROM nginx:alpine
ARG APP=hr-web
COPY --from=build /src/frontend/apps/${APP}/dist /usr/share/nginx/html
COPY deploy/nginx.conf /etc/nginx/conf.d/default.conf
