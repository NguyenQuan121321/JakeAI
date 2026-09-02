import typescript from '@rollup/plugin-typescript';
import resolve from '@rollup/plugin-node-resolve';
import commonjs from '@rollup/plugin-commonjs';
import terser from '@rollup/plugin-terser';

export default [
  // 1. React Component Library (ESM)
  {
    input: 'src/index.ts',
    output: {
      file: 'dist/index.js',
      format: 'es',
      sourcemap: true
    },
    external: ['react', 'react-dom', 'react/jsx-runtime'],
    plugins: [
      resolve(),
      commonjs(),
      typescript({
        tsconfig: './tsconfig.json',
        declaration: true,
        declarationDir: './dist'
      })
    ]
  },
  // 2. Standalone Single-File Bundle (IIFE)
  {
    input: 'src/standalone.ts',
    output: [
      {
        file: 'dist/jake.js',
        format: 'iife',
        name: 'JakeAI'
      },
      {
        file: 'dist/jake.min.js',
        format: 'iife',
        name: 'JakeAI',
        plugins: [
          terser({
            format: {
              comments: false,
              preamble: '/*! JakeAI v1.0.0 (TypeScript) | MIT License | Interactive Corgi Companion */'
            }
          })
        ]
      }
    ],
    plugins: [
      resolve(),
      commonjs(),
      typescript({
        tsconfig: './tsconfig.json',
        declaration: false
      })
    ]
  }
];
