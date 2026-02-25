FROM node:20-alpine

WORKDIR /app

COPY ui/package.json /app/package.json
RUN npm install

COPY ui /app

RUN npm run build

EXPOSE 3000
CMD ["npm", "run", "start"]
