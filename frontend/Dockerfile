FROM node:22-slim

WORKDIR /app

# Install dependencies first for better layer caching.
COPY package.json package-lock.json* ./
RUN npm install

COPY . .

EXPOSE 5173

# Dev server by default; production compose overrides with `build && preview`.
CMD ["npm", "run", "dev", "--", "--host", "0.0.0.0", "--port", "5173"]
