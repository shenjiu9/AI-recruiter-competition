// 前端依赖边界（实现文档第 8 节）：app → pages → features → packages，功能切片之间不得互相引用内部代码。
import js from '@eslint/js';
import tseslint from 'typescript-eslint';
import boundaries from 'eslint-plugin-boundaries';
import reactHooks from 'eslint-plugin-react-hooks';
import globals from 'globals';

export default tseslint.config(
  { ignores: ['**/dist/**', '**/node_modules/**'] },
  js.configs.recommended,
  ...tseslint.configs.recommended,
  {
    files: ['frontend/**/*.{ts,tsx}'],
    languageOptions: { globals: globals.browser },
    plugins: { boundaries, 'react-hooks': reactHooks },
    settings: {
      'boundaries/include': ['frontend/**/*'],
      'boundaries/elements': [
        { type: 'app', pattern: 'frontend/apps/*/src/app/**', mode: 'full' },
        { type: 'pages', pattern: 'frontend/apps/*/src/pages/**', mode: 'full' },
        { type: 'feature', pattern: 'frontend/apps/*/src/features/*', capture: ['feature'] },
        { type: 'shared', pattern: 'frontend/apps/*/src/shared/**', mode: 'full' },
        { type: 'package', pattern: 'frontend/packages/*', capture: ['pkg'] },
      ],
    },
    rules: {
      ...reactHooks.configs.recommended.rules,
      '@typescript-eslint/no-explicit-any': 'error',
      'boundaries/element-types': [
        'error',
        {
          default: 'disallow',
          rules: [
            { from: 'app', allow: ['pages', 'feature', 'shared', 'package', 'app'] },
            { from: 'pages', allow: ['feature', 'shared', 'package', 'pages'] },
            // 功能切片只能引用自己、shared 和 packages；需要别的功能的东西就下沉到 packages
            { from: 'feature', allow: [['feature', { feature: '${from.feature}' }], 'shared', 'package'] },
            { from: 'shared', allow: ['shared', 'package'] },
            { from: 'package', allow: ['package'] },
          ],
        },
      ],
    },
  },
);
