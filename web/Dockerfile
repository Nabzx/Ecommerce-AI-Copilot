FROM node:20-slim AS builder

WORKDIR /app

COPY package.json package-lock.json ./
RUN npm ci

COPY . .

# Baked in at build time, not read at runtime — Next inlines NEXT_PUBLIC_*
# into the bundle, so it has to be present now rather than in compose.
ARG NEXT_PUBLIC_API_URL=http://localhost:8000
ENV NEXT_PUBLIC_API_URL=$NEXT_PUBLIC_API_URL

RUN npm run build

# --- runtime ---
# Only the built output and production dependencies come across.
FROM node:20-slim

WORKDIR /app
ENV NODE_ENV=production

COPY --from=builder /app/package.json /app/package-lock.json ./
RUN npm ci --omit=dev

COPY --from=builder /app/.next ./.next
# No public/ directory in this project — every asset is inlined or generated,
# and copying a folder that doesn't exist fails the build outright rather than
# being skipped. Add the COPY back alongside the folder if one appears.

EXPOSE 3000

CMD ["npm", "start"]
