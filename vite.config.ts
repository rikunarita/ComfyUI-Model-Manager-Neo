import vue from '@vitejs/plugin-vue'
import fs from 'node:fs'
import path from 'node:path'
import { defineConfig, Plugin } from 'vite'

function cssLoader(): Plugin {
  return {
    name: 'vite-plugin-css-loader',
    apply: 'build',
    enforce: 'post',
    generateBundle(_, bundle) {
      let cssFileName = ''
      for (const key in bundle) {
        const chunk = bundle[key]
        if (chunk.type === 'asset' && chunk.fileName.endsWith('.css')) {
          cssFileName = chunk.fileName
        }
      }
      if (!cssFileName) return
      for (const key in bundle) {
        const chunk = bundle[key]
        if (chunk.type === 'chunk' && chunk.fileName === 'manager.js') {
          const originalCode = chunk.code
          const loaderCode = `
(async()=>{try{const c=await fetch(new URL("./${cssFileName}",import.meta.url).href);if(c.ok){const s=document.createElement("style");s.textContent=await c.text();document.head.appendChild(s)}}catch(e){console.warn("Model Manager Neo: CSS load failed",e)}})();
`
          chunk.code = loaderCode + originalCode
        }
      }
    },
  }
}

function output(): Plugin {
  return {
    name: 'vite-plugin-output-fix',
    apply: 'build',
    enforce: 'post',
    generateBundle(_, bundle) {
      for (const key in bundle) {
        const chunk = bundle[key]
        if (chunk.type === 'asset' && chunk.fileName === 'index.html') {
          delete bundle[key]
        }
        if (chunk.fileName.startsWith('assets/')) {
          chunk.fileName = chunk.fileName.replace('assets/', '')
        }
      }
    },
  }
}

function dev(): Plugin {
  return {
    name: 'vite-plugin-dev-fix',
    apply: 'serve',
    enforce: 'post',
    configureServer(server) {
      server.httpServer?.on('listening', () => {
        const rootDir = server.config.root
        const outDir = server.config.build.outDir
        const outDirPath = path.join(rootDir, outDir)
        if (fs.existsSync(outDirPath)) {
          fs.rmSync(outDirPath, { recursive: true })
        }
        fs.mkdirSync(outDirPath)
        const port = server.config.server.port
        const content = `import "http://localhost:${port}/src/main.ts";\nimport "http://localhost:${port}/src/style.css";`
        fs.writeFileSync(path.join(outDirPath, 'manager-dev.js'), content)
      })
    },
  }
}

function createWebVersion(): Plugin {
  return {
    name: 'vite-plugin-web-version',
    apply: 'build',
    enforce: 'post',
    writeBundle() {
      const pyProjectContent = fs.readFileSync('pyproject.toml', 'utf8')
      const [, version] = pyProjectContent.match(/version = "(.*)"/) ?? []
      const metadata = [
        `version: ${version}`,
        `build_time: ${new Date().toISOString()}`,
        '',
      ].join('\n')
      const metadataFilePath = path.join(__dirname, 'web', 'version.yaml')
      fs.writeFileSync(metadataFilePath, metadata, 'utf-8')
    },
  }
}

export default defineConfig({
  plugins: [vue(), cssLoader(), output(), dev(), createWebVersion()],

  // vue-i18n feature flags（tree-shaking 最適化。v11 公式推奨）
  define: {
    __VUE_I18N_FULL_INSTALL__: false,
    __VUE_I18N_LEGACY_API__: false,
    __INTLIFY_PROD_DEVTOOLS__: false,
  },

  build: {
    outDir: 'web',
    target: 'es2022',
    sourcemap: false,
    cssCodeSplit: false,
    // Vite 8: rollupOptions → rolldownOptions へ移行
    // manualChunks は Vite 8 で削除/非推奨のため廃止（単一チャンク化。
    // ComfyUI WEB_DIRECTORY が全 .js を読む仕様上、別チャンクを持たない方が安全）
    rolldownOptions: {
      treeshake: true,
      output: {
        entryFileNames: 'manager.js',
        chunkFileNames: '[name]-[hash].js',
        assetFileNames: '[name]-[hash].[ext]',
        keepNames: true,
      },
    },
    chunkSizeWarningLimit: 1024,
  },

  resolve: {
    dedupe: ['primevue', '@primevue/themes', '@primeuix/styled', '@primeuix/utils'],
    alias: {
      src: resolvePath('src'),
      components: resolvePath('src/components'),
      hooks: resolvePath('src/hooks'),
      scripts: resolvePath('src/scripts'),
      types: resolvePath('src/types'),
      utils: resolvePath('src/utils'),
    },
  },
})

function resolvePath(str: string) {
  return path.resolve(__dirname, str)
}
