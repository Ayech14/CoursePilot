# Development image. A production build served by a web server arrives in Milestone 6.
FROM node:26-alpine

WORKDIR /app

COPY package.json package-lock.json ./
RUN npm ci --no-fund --no-audit

COPY . .

EXPOSE 5173
CMD ["npm", "run", "dev"]
