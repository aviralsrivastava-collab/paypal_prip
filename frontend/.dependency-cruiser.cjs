/** @type {import('dependency-cruiser').IConfiguration} */
module.exports = {
  forbidden: [
    {
      name: 'no-backend-imports',
      comment: 'Frontend code must NEVER import directly from backend application files.',
      severity: 'error',
      from: { path: '^src' },
      to: { path: '(\\.\\./)*backend' }
    },
    {
      name: 'no-circular',
      comment: 'Circular dependencies across frontend files are strictly forbidden.',
      severity: 'error',
      from: {},
      to: { circular: true }
    },
    {
      name: 'components-do-not-import-pages',
      comment: 'Shared presentational components must not import from full view pages.',
      severity: 'error',
      from: { path: '^src/components' },
      to: { path: '^src/pages' }
    },
    {
      name: 'components-do-not-import-services',
      comment: 'Shared presentational components must not import API services directly.',
      severity: 'error',
      from: { path: '^src/components' },
      to: { path: '^src/services' }
    }
  ],
  options: {
    doNotFollow: {
      path: 'node_modules'
    },
    tsPreCompilationDeps: true,
    tsConfig: {
      fileName: './tsconfig.json'
    }
  }
};
