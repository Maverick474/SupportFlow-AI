FROM node:22-alpine

WORKDIR /app

ENV BACKEND_TARGET=http://server:8000

COPY package.json ./
RUN npm install --package-lock=false

COPY index.html vite.config.js ./
COPY public ./public
COPY src ./src
RUN npm run build

EXPOSE 4173

CMD ["npm", "run", "preview", "--", "--host", "0.0.0.0", "--port", "4173"]
