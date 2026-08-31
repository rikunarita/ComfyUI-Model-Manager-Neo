import vue from '@vitejs/plugin-vue'
import fs from 'node:fs'
import path from 'node:path'
import { defineConfig, Plugin } from 'vite'

// CSSをJSに埋め込むIIFEプラグインを完全削除。
// Viteの標準機能で web/manager.css として出力させ、ComfyUIに自動読み込みさせる。

function output(): Plugin {
  return {
    name: 'vite-plugin-output-fix',
    apply: 'build',
    enforce: 'post',
    generateBundle(_, bundle) {
      for (const key in bundle) {
        const chunk = bundle[key]

        if (chunk.type === 'asset') {
          if (chunk.fileName === 'index.html') {
            delete bundle[key]
          }
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
        // 開発時はJSとCSSの両方を読み込む
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
  // css() プラグインを配列から削除
  plugins: [vue(), output(), dev(), createWebVersion()],

  build: {
    outDir: 'web',
    minify: 'esbuild',
    target: 'es2022',
    sourcemap: false,
    // CSSを別ファイルに抽出する設定を明示（Viteのデフォルト動作を確保）
    cssCodeSplit: false,
    rollupOptions: {
      treeshake: true,
      output: {
        entryFileNames: 'manager.js',
        chunkFileNames: '[name]-[hash].js',
        // CSSファイル名を固定して ComfyUI に認識させる
        assetFileNames: (assetInfo) => {
          if (assetInfo.name && assetInfo.name.endsWith('.css')) {
            return 'manager.css'
          }
          return '[name]-[hash].[ext]'
        },
        manualChunks(id) {
          if (id.includes('primevue')) {
            return 'primevue'
          }
        },
      },
    },
    chunkSizeWarningLimit: 1024,
  },

  resolve: {
    alias: {
      src: resolvePath('src'),
      components: resolvePath('src/components'),
      hooks: resolvePath('src/hooks'),
      scripts: resolvePath('src/scripts'),
      types: resolvePath('src/types'),
      utils: resolvePath('src/utils'),
    },
  },

  esbuild: {
    minifyIdentifiers: false,
    keepNames: true,
    minifySyntax: true,
    minifyWhitespace: true,
  },
})

function resolvePath(str: string) {
  return path.resolve(__dirname, str)
}
