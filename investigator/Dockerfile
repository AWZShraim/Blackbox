# Multi-stage build for the Investigator (Next.js). Server env vars
# (RECORDER_URL, MEDIATOR_URL, DEMO_URL, BLACKBOX_OPERATOR_KEY) are read at
# runtime by the app/api/* route handlers — they are never bundled into
# client-side JS, which is the whole point of routing through them
# (Section 6.5 / M9's containment control).
FROM node:20-slim AS build
WORKDIR /app
COPY package.json package-lock.json ./
RUN npm ci
COPY . .
RUN npm run build

FROM node:20-slim
WORKDIR /app
ENV NODE_ENV=production
COPY --from=build /app/.next ./.next
COPY --from=build /app/public ./public
COPY --from=build /app/package.json ./package.json
COPY --from=build /app/node_modules ./node_modules
EXPOSE 3000
CMD ["npm", "run", "start"]
