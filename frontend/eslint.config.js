import js from '@eslint/js'
import vue from 'eslint-plugin-vue'
import tseslint from 'typescript-eslint'

export default tseslint.config(
  { ignores: ['dist', 'node_modules', 'qa', 'e2e', 'coverage'] },
  js.configs.recommended,
  ...tseslint.configs.recommended,
  ...vue.configs['flat/recommended'],
  {
    files: ['**/*.vue'],
    languageOptions: { parserOptions: { parser: tseslint.parser } },
  },
  {
    rules: {
      // markup style is not worth lint noise; the structure rules stay on
      'vue/max-attributes-per-line': 'off',
      'vue/singleline-html-element-content-newline': 'off',
      'vue/multiline-html-element-content-newline': 'off',
      'vue/html-self-closing': 'off',
      'vue/html-indent': 'off',
      'vue/html-closing-bracket-newline': 'off',
      'vue/first-attribute-linebreak': 'off',
      'vue/attributes-order': 'off',
      'vue/multi-word-component-names': 'off',
      'no-irregular-whitespace': 'off', // vue/no-irregular-whitespace covers templates
      // TypeScript already knows every global; the browser ones would all need listing otherwise
      'no-undef': 'off',
      // the full-width space (U+3000) is ordinary Chinese typography in visible text
      'vue/no-irregular-whitespace': ['error', { skipHTMLTextContents: true, skipStrings: true, skipTemplates: true }],
      // the post body is sanitised HTML from the server (Markdown pipeline + allow-list)
      'vue/no-v-html': 'off',
      '@typescript-eslint/no-unused-vars': ['error', { argsIgnorePattern: '^_', varsIgnorePattern: '^_' }],
      '@typescript-eslint/no-explicit-any': 'error',
      'no-console': ['error', { allow: ['warn', 'error'] }],
      eqeqeq: ['error', 'always'],
    },
  },
  {
    // boot.js is a plain ES5 script that runs before the app: no optional catch bindings
    files: ['src/public/boot.js'],
    languageOptions: { sourceType: 'script', ecmaVersion: 5 },
    rules: { '@typescript-eslint/no-unused-vars': ['error', { caughtErrors: 'none' }], 'no-var': 'off', 'prefer-const': 'off' },
  },
  {
    // command-line scripts print their report
    files: ['scripts/**/*.mjs'],
    languageOptions: { globals: { process: 'readonly' } },
    rules: { 'no-console': 'off' },
  },
)
