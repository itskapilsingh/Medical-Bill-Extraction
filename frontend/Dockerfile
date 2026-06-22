# --- deps -------------------------------------------------------------------
FROM node:22-alpine AS deps
WORKDIR /app
COPY package.json package-lock.json* ./
RUN npm ci

# --- build ------------------------------------------------------------------
FROM node:22-alpine AS builder
WORKDIR /app
ENV NEXT_TELEMETRY_DISABLED=1
# Build-time placeholders so the bundle never depends on runtime secrets. Real
# values are injected at runtime via env_file in docker-compose.yml.
ENV BETTER_AUTH_SECRET=build-time-placeholder
ENV BETTER_AUTH_URL=http://localhost:3000
ENV DATABASE_URL=postgres://placeholder:placeholder@localhost:5432/placeholder
COPY --from=deps /app/node_modules ./node_modules
COPY . .
RUN npm run build

# --- runtime ----------------------------------------------------------------
FROM node:22-alpine AS runner
WORKDIR /app
ENV NODE_ENV=production
ENV NEXT_TELEMETRY_DISABLED=1
ENV PORT=3000
ENV HOSTNAME=0.0.0.0

RUN addgroup -g 1001 -S nodejs && adduser -S nextjs -u 1001

# Next.js standalone output: a self-contained server with a minimal node_modules.
COPY --from=builder /app/public ./public
COPY --from=builder --chown=nextjs:nodejs /app/.next/standalone ./
COPY --from=builder --chown=nextjs:nodejs /app/.next/static ./.next/static

USER nextjs
EXPOSE 3000
CMD ["node", "server.js"]
