const { createServer } = require('http');
const { parse } = require('url');
const next = require('next');

const dev = process.env.NODE_ENV !== 'production';
const NEXT_PORT = parseInt(process.env.PORT || '3000', 10);
const OAUTH_PORT = parseInt(process.env.OAUTH_PORT || '1455', 10);

const app = next({ dev });
const handle = app.getRequestHandler();

app.prepare().then(() => {
  createServer((req, res) => {
    const parsedUrl = parse(req.url, true);
    handle(req, res, parsedUrl);
  }).listen(NEXT_PORT, '0.0.0.0', () => {
    console.log(`> Next.js ready on http://localhost:${NEXT_PORT}`);
  }).on('error', (err) => {
    console.error(`Next.js server error (port ${NEXT_PORT}):`, err.message);
    process.exit(1);
  });

  createServer((req, res) => {
    const { pathname, query } = parse(req.url, true);
    if (pathname === '/auth/callback') {
      const code = query.code || '';
      const state = query.state || '';
      const target = `http://localhost:${NEXT_PORT}/api/auth/exchange?code=${encodeURIComponent(code)}&state=${encodeURIComponent(state)}`;
      res.writeHead(302, { Location: target });
      res.end();
    } else {
      res.writeHead(404);
      res.end('Not found');
    }
  }).listen(OAUTH_PORT, '0.0.0.0', () => {
    console.log(`> OAuth callback receiver ready on http://localhost:${OAUTH_PORT}`);
  }).on('error', (err) => {
    console.error(`OAuth server error (port ${OAUTH_PORT}):`, err.message);
    process.exit(1);
  });
}).catch((err) => {
  console.error('Failed to start server:', err);
  process.exit(1);
});
