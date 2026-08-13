# syntax=docker/dockerfile:1.7

FROM node:22-alpine AS deps
WORKDIR /app
COPY package.json package-lock.json* ./
RUN npm ci --omit=dev --ignore-scripts || npm install --omit=dev --ignore-scripts

FROM node:22-alpine AS builder
WORKDIR /app
COPY package.json package-lock.json* ./
RUN npm ci --ignore-scripts || npm install --ignore-scripts
COPY . .

# NEXT_PUBLIC_* values are inlined into the client bundle at build time, so the API URL
# must be supplied here and must match what the running middleware puts in the CSP
# connect-src. A mismatch shows up as the browser refusing every API call.
ARG NEXT_PUBLIC_API_URL=http://localhost:8000
ENV NEXT_PUBLIC_API_URL=$NEXT_PUBLIC_API_URL

# The build refuses to bake a localhost API URL into a public bundle, which is the whole
# point of the guard — but the ARG default above is localhost, for `docker compose up`.
# So a local build has to be able to say "yes, deliberately", and this is how.
#
# Defaulted to false rather than true on purpose. `docker build ./frontend` with no
# arguments is far more likely to be someone building for deployment than someone
# building for their laptop, and that person needs the error. docker-compose.yml opts in
# explicitly because it genuinely does mean localhost; the production overlay never sets
# it, so the guard stays live exactly where it earns its keep.
ARG NEXT_PUBLIC_ALLOW_LOCALHOST=false
ENV NEXT_PUBLIC_ALLOW_LOCALHOST=$NEXT_PUBLIC_ALLOW_LOCALHOST

# Optional. Empty means the /tools page says the chart embeds are not configured rather
# than rendering a widget with a placeholder affiliate id.
ARG NEXT_PUBLIC_ASTRO_CHARTS_AFF=
ENV NEXT_PUBLIC_ASTRO_CHARTS_AFF=$NEXT_PUBLIC_ASTRO_CHARTS_AFF
ENV NEXT_TELEMETRY_DISABLED=1

RUN npm run build

FROM node:22-alpine AS runtime
WORKDIR /app

ENV NODE_ENV=production NEXT_TELEMETRY_DISABLED=1 PORT=3000

RUN addgroup -g 1001 -S nodejs && adduser -S nextjs -u 1001

COPY --from=builder --chown=nextjs:nodejs /app/.next ./.next
COPY --from=builder --chown=nextjs:nodejs /app/public ./public
COPY --from=deps --chown=nextjs:nodejs /app/node_modules ./node_modules
COPY --chown=nextjs:nodejs package.json next.config.mjs ./

USER nextjs
EXPOSE 3000

HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
    CMD wget --no-verbose --tries=1 --spider http://localhost:3000/ || exit 1

CMD ["npx", "next", "start"]
