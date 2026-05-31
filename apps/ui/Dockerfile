FROM node:20-slim

WORKDIR /react-app
COPY react-app/package*.json /react-app/
RUN npm ci
COPY react-app/ /react-app/
CMD ["npm", "run", "dev", "--", "--host", "0.0.0.0", "--port", "5173"]
