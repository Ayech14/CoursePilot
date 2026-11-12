# Development image. Production uses ../Dockerfile, where the API serves the built app.
FROM node:26-alpine

WORKDIR /app

COPY package.json package-lock.json ./
RUN npm ci --no-fund --no-audit

COPY . .

EXPOSE 5173
CMD ["npm", "run", "dev"]
