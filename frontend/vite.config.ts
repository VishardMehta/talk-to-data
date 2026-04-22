import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import tailwindcss from '@tailwindcss/vite'
import path from 'path'

/**
 * Vite configuration for Talk-To-Data frontend.
 *
 * Dev server proxy:
 *   Any request to /api/... is forwarded to the FastAPI backend on port 8000.
 *   This means the browser never makes a cross-origin request, so CORS is a
 *   non-issue in local development.  The frontend just uses relative URLs like
 *   "/api/health" and Vite handles the forwarding transparently.
 *
 * How to run:
 *   Backend:  uvicorn api.server:app --reload --port 8000   (from project root)
 *   Frontend: npm run dev                                    (from frontend/)
 */
export default defineConfig({
  plugins: [react(), tailwindcss()],
  resolve: {
    alias: {
      '@': path.resolve(__dirname, './src'),
    },
  },
  server: {
    port: 5173,
    proxy: {
      // Forward every /api/* request to the FastAPI backend.
      // changeOrigin rewrites the Host header so FastAPI sees localhost:8000.
      '/api': {
        target: 'http://127.0.0.1:8000',
        changeOrigin: true,
        // SSE streams must not be buffered — disable response buffering.
        configure: (proxy) => {
          proxy.on('proxyReq', (_proxyReq, req) => {
            if (req.headers.accept?.includes('text/event-stream')) {
              // SSE: let the stream pass through without buffering
            }
          })
        },
      },
    },
  },
})
