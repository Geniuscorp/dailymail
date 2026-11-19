import colors from 'tailwindcss/colors'

// Every colour the UI uses is read from a CSS variable with the light value as its
// fallback, so the light theme is exactly Tailwind's default palette and the dark
// theme only has to override variables (see src/index.css). Components keep using
// plain classes such as `bg-white` or `text-gray-500` and follow the theme for free.
const toRgb = (hex) => {
  const n = parseInt(hex.slice(1), 16)
  return `${(n >> 16) & 255} ${(n >> 8) & 255} ${n & 255}`
}

const themed = (name) =>
  Object.fromEntries(
    Object.entries(colors[name]).map(([shade, hex]) => [
      shade,
      `rgb(var(--c-${name}-${shade}, ${toRgb(hex)}) / <alpha-value>)`,
    ]),
  )

/** @type {import('tailwindcss').Config} */
export default {
  darkMode: 'class',
  content: [
    "./index.html",
    "./src/**/*.{js,ts,jsx,tsx}",
  ],
  theme: {
    extend: {
      colors: {
        gray: themed('gray'),
        indigo: themed('indigo'),
        red: themed('red'),
        emerald: themed('emerald'),
        amber: themed('amber'),
        violet: themed('violet'),
        sky: themed('sky'),
        rose: themed('rose'),
        // Card/surface colour: white in light mode, a raised dark panel in dark mode.
        white: 'rgb(var(--c-surface, 255 255 255) / <alpha-value>)',
        // Text/fill that must stay white on an accent background in both themes.
        onaccent: '#ffffff',
      },
    },
  },
  plugins: [],
}
