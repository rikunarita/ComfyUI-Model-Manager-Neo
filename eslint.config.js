/**
 * ESLint flat config for ComfyUI-Model-Manager-Neo.
 *
 * Layers (in order):
 *   1. ignores                — build artifacts & binaries
 *   2. typescript-eslint      — recommended TS/JS rules
 *   3. eslint-plugin-vue      — flat/recommended (via vue-eslint-parser)
 *   4. eslint-plugin-tailwindcss — Tailwind v4 class hygiene
 *   5. eslint-plugin-import-x — import hygiene & ordering (alias-aware)
 *   6. project overrides      — parsers, globals, rule tuning
 *   7. eslint-config-prettier — MUST stay last: disables stylistic rules
 *                               that would conflict with Prettier
 *
 * Class *ordering* is delegated to prettier-plugin-tailwindcss (see .prettierrc)
 * so the two tools never fight over the same attribute.
 */
import path from 'node:path'
import { fileURLToPath } from 'node:url'
import eslintConfigPrettier from 'eslint-config-prettier'
import importX from 'eslint-plugin-import-x'
import tailwindcss from 'eslint-plugin-tailwindcss'
import pluginVue from 'eslint-plugin-vue'
import globals from 'globals'
import tseslint from 'typescript-eslint'
import vueParser from 'vue-eslint-parser'

const dirname = path.dirname(fileURLToPath(import.meta.url))

export default tseslint.config(
  {
    name: 'mm-neo/ignores',
    ignores: [
      'web/**',
      'demo/**',
      'assets/**',
      'node_modules/**',
      'dist/**',
      'coverage/**',
      '**/*.tsbuildinfo',
      'pnpm-lock.yaml',
    ],
  },

  // ---- TypeScript / JavaScript ------------------------------------------------
  ...tseslint.configs.recommended,

  // ---- Vue SFCs (flat/recommended wires vue-eslint-parser internally) ---------
  ...pluginVue.configs['flat/recommended'],

  // ---- Tailwind CSS v4 ---------------------------------------------------------
  tailwindcss.configs.recommended,

  // ---- Imports -----------------------------------------------------------------
  {
    name: 'mm-neo/import-x',
    files: ['**/*.{js,mjs,cjs,ts,mts,cts,tsx,vue}'],
    plugins: { 'import-x': importX },
    settings: {
      'import-x/resolver-next': [
        importX.createNodeResolver({
          extensions: ['.mjs', '.cjs', '.js', '.jsx', '.ts', '.tsx', '.vue', '.json'],
          tsconfig: { configFile: path.resolve(dirname, 'tsconfig.json') },
        }),
      ],
      // Vite/tsconfig path aliases count as internal imports
      'import-x/internal-regex': '^(src|components|hooks|scripts|types|utils)/',
    },
    rules: {
      'import-x/first': 'error',
      'import-x/newline-after-import': 'error',
      'import-x/no-duplicates': ['error', { considerQueryString: true }],
      'import-x/no-self-import': 'error',
      'import-x/no-useless-path-segments': 'error',
      'import-x/order': [
        'error',
        {
          groups: [
            'builtin',
            'external',
            'internal',
            'parent',
            'sibling',
            'index',
            'object',
            'type',
          ],
          alphabetize: { order: 'asc', caseInsensitive: true },
          'newlines-between': 'never',
        },
      ],
      'import-x/consistent-type-specifier-style': ['error', 'prefer-inline'],
    },
  },

  // ---- Parsers -------------------------------------------------------------------
  {
    name: 'mm-neo/parser-vue',
    files: ['**/*.vue'],
    languageOptions: {
      parser: vueParser,
      parserOptions: {
        parser: tseslint.parser,
        ecmaVersion: 'latest',
        sourceType: 'module',
        extraFileExtensions: ['.vue'],
      },
    },
  },

  // ---- Project-wide options & rule tuning -----------------------------------------
  {
    name: 'mm-neo/rules',
    files: ['**/*.{js,mjs,cjs,ts,mts,cts,tsx,vue}'],
    languageOptions: {
      ecmaVersion: 'latest',
      sourceType: 'module',
      globals: {
        ...globals.browser,
        ...globals.node,
      },
    },
    settings: {
      tailwindcss: {
        // Tailwind v4 entry point (theme tokens, custom utilities, layers)
        cssConfigPath: './src/style.css',
      },
    },
    rules: {
      // Vue -------------------------------------------------------------------
      // Single-word component names are the norm for dialog/response components
      'vue/multi-word-component-names': 'off',
      // Markdown descriptions are rendered intentionally
      'vue/no-v-html': 'off',
      // Both template-first (app components) and script-first (ui/ library,
      // shadcn-vue convention) SFC layouts are used deliberately
      'vue/block-order': 'off',
      // reka-ui wrapper components intentionally forward optional props
      // (class, modelValue, …) without defaults — shadcn-vue convention
      'vue/require-default-prop': 'off',

      // TypeScript --------------------------------------------------------------
      '@typescript-eslint/no-explicit-any': 'off',
      '@typescript-eslint/no-unused-vars': [
        'warn',
        {
          argsIgnorePattern: '^_',
          varsIgnorePattern: '^_',
          caughtErrors: 'none',
        },
      ],

      // Tailwind -------------------------------------------------------------------
      // Ordering is owned by prettier-plugin-tailwindcss — keep exactly one sorter
      'tailwindcss/classnames-order': 'off',
      'tailwindcss/no-custom-classname': [
        'warn',
        {
          whitelist: [
            // Design-system helpers defined in src/style.css (@layer mm-components)
            '^mm(-.+)?$',
            // Misc project-scoped classes
            '^(preview-aspect|scrollbar-none|text-shadow|icon|dark-theme|markdown-body)$',
          ],
        },
      ],

      // Core ----------------------------------------------------------------------
      'no-empty': ['error', { allowEmptyCatch: true }],
    },
  },

  // ---- MUST be last ---------------------------------------------------------------
  eslintConfigPrettier,
)
