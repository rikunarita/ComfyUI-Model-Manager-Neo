/** @type {import('dependency-cruiser').IConfiguration} */
/*
 * Module-graph guard for the Vue 3 frontend (`src/`).
 *
 * Complements ESLint (inside files) and Fallow (dead code & duplication):
 * dependency-cruiser validates the IMPORT GRAPH itself. The rule set is the
 * shipped `recommended-strict` preset inlined (v18's package exports do not
 * expose the preset for `extends`) - no cycles, no orphans, nothing
 * unresolvable, no deprecated core modules or npm packages, no packages
 * outside package.json, no duplicate dependency types - plus two project
 * rules: app code never imports devDependencies or Node core modules.
 *
 * Run: pnpm deps        (validate)
 *      pnpm deps:graph  (write dependency_graph.svg)
 * Requires Node >= 22 (dependency-cruiser 18); CI runs it on Node 22.
 */

const KNOWN_CONFIG_FILE_PATTERNS = [
  '(^|/)\\.[^/]+\\.(js|cjs|mjs|ts|json)$', // dotfiles
  '\\.d\\.(c|m)?ts$', // TypeScript declaration files
  '(^|/)tsconfig\\.json$',
  '(^|/)(?:babel|webpack)\\.config\\.(?:js|cjs|mjs|ts|json)$',
].join('|')

export default {
  forbidden: [
    {
      name: 'no-circular',
      comment:
        'This dependency is part of a circular relationship. Cycles make HMR ' +
        'unreliable, blur module initialization order and trap imports in TDZ ' +
        'errors - hooks/modelDetail exists precisely to break the historic ' +
        'model <-> DialogModelDetail cycle; keep it that way.',
      severity: 'error',
      from: {},
      to: { circular: true },
    },
    {
      name: 'no-orphans',
      comment:
        "This is an orphan module - it's likely not used (anymore?). Either use " +
        'it or remove it. Known config/declaration files are exempt.',
      severity: 'error',
      from: { orphan: true, pathNot: KNOWN_CONFIG_FILE_PATTERNS },
      to: {},
    },
    {
      name: 'no-deprecated-core',
      comment: 'Depends on a deprecated node core module.',
      severity: 'error',
      from: {},
      to: {
        dependencyTypes: ['core'],
        path: '^(?:punycode|domain|constants|sys|_linklist|_stream_wrap)$',
      },
    },
    {
      name: 'no-duplicate-dep-types',
      comment:
        'Depends on an external package that occurs more than once in ' +
        'package.json (e.g. both dev and regular) - a maintenance trap.',
      severity: 'error',
      from: {},
      to: {
        moreThanOneDependencyType: true,
        dependencyTypesNot: ['type-only'],
      },
    },
    {
      name: 'no-non-package-json',
      comment:
        "Depends on an npm package that isn't in package.json - it either " +
        "won't be available in production or lands with an unguaranteed version.",
      severity: 'error',
      from: {},
      to: { dependencyTypes: ['npm-no-pkg', 'npm-unknown'] },
    },
    {
      name: 'not-to-deprecated',
      comment: 'Uses a deprecated npm package (a security risk).',
      severity: 'error',
      from: {},
      to: { dependencyTypes: ['deprecated'] },
    },
    {
      name: 'not-to-unresolvable',
      comment:
        'Depends on a module that cannot be resolved to disk (typo, moved ' +
        'file, missing alias) - a build/runtime break waiting to happen.',
      severity: 'error',
      from: {},
      to: { couldNotResolve: true },
    },
    {
      name: 'not-to-dev-dep',
      comment:
        'Shipped code must not import devDependencies - they are absent from ' +
        'production installs. Type-only imports inside .d.ts files are fine.',
      severity: 'error',
      from: { path: '^src', pathNot: '\\.d\\.ts$' },
      to: {
        dependencyTypes: ['npm-dev'],
        pathNot: ['node_modules/@types/'],
      },
    },
    {
      name: 'no-node-core-in-app',
      comment:
        'The bundle runs in the browser: Node core modules have no business ' +
        'in src/ (build/tooling configs live outside includeOnly).',
      severity: 'error',
      from: { path: '^src' },
      to: { dependencyTypes: ['core'] },
    },
  ],
  options: {
    doNotFollow: {
      path: 'node_modules',
      dependencyTypes: ['npm', 'npm-dev', 'npm-optional', 'npm-peer', 'npm-bundled', 'npm-no-pkg'],
    },
    tsConfig: {
      fileName: 'tsconfig.json',
    },
    includeOnly: '^src',
    enhancedResolveOptions: {
      exportsFields: ['exports'],
      conditionNames: ['import', 'require', 'node', 'default', 'browser'],
      extensions: ['.ts', '.js', '.mjs', '.json', '.vue'],
      mainFields: ['module', 'browser', 'main'],
    },
    reporterOptions: {
      dot: {
        collapsePattern: 'node_modules/(@[^/]+/[^/]+|[^/]+)',
      },
    },
  },
}
