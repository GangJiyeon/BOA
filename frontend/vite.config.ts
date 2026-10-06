import react from '@vitejs/plugin-react'
import { defineConfig } from 'vite'

// https://vite.dev/config/
export default defineConfig({
  plugins: [react()],
  server: {
    // 프론트 코드는 항상 /api/... 로 호출하고, 로컬에서는 Vite가 FastAPI로 넘겨준다.
    // 배포 후에는 Vercel rewrites가 같은 역할을 한다.
    proxy: {
      '/api': 'http://localhost:8000',
      '/static': 'http://localhost:8000',
    },
  },
})
