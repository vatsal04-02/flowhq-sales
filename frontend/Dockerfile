FROM node:22-slim AS build
WORKDIR /app
COPY package*.json ./
RUN npm ci
COPY . .
# next.config.js bakes the /api/v1 proxy target into the build, so it must be known here, not at container start.
ARG API_URL=http://api:8000
ENV API_URL=$API_URL
RUN npm run build
FROM node:22-slim
WORKDIR /app
ENV NODE_ENV=production
COPY --from=build /app/.next/standalone ./
COPY --from=build /app/.next/static ./.next/static
EXPOSE 3000
CMD ["node", "server.js"]
