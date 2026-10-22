/** @type {import('tailwindcss').Config} */

// PitchPulse graphics package: matchday ink, chalk-white type, a red "pulse"
// and a floodlight yellow. Square-cut corners and condensed type, like a
// stadium scoreboard rather than an app template.
const warm = {
  50: '#f6f4ef',
  100: '#ece9e1',
  200: '#d9d5ca',
  300: '#bdb8ab',
  400: '#9b9688',
  500: '#7a7569',
  600: '#5c5850',
  700: '#43403a',
  800: '#2b2925',
  900: '#1b1a17',
  950: '#100f0d',
};

export default {
  content: ['./index.html', './src/**/*.{js,ts,jsx,tsx}'],
  theme: {
    borderRadius: {
      none: '0',
      sm: '1px',
      DEFAULT: '2px',
      md: '2px',
      lg: '3px',
      xl: '3px',
      '2xl': '4px',
      '3xl': '4px',
      full: '9999px',
    },
    boxShadow: {
      none: 'none',
      sm: 'none',
      DEFAULT: 'none',
      md: 'none',
      lg: '0 0 0 1px rgba(242,239,232,0.04)',
      xl: '0 0 0 1px rgba(242,239,232,0.06)',
      '2xl': '0 0 0 1px rgba(242,239,232,0.08)',
      inner: 'none',
    },
    extend: {
      colors: {
        slate: warm,
        pp: {
          night: '#0c0c0b',
          deep: '#121210',
          panel: '#181815',
          raised: '#22221e',
          line: '#34332d',
          mute: '#a19c8f',
          chalk: '#f2efe8',
          pulse: '#ff3b2f',
          pulseSoft: '#ff8a80',
          signal: '#ffd400',
          gold: '#ff9f1c',
          turf: '#14301f',
          turfLine: '#5f9a72',
        },
      },
      fontFamily: {
        display: ['"Barlow Condensed"', 'Cairo', 'sans-serif'],
        sans: ['Barlow', '"IBM Plex Sans Arabic"', 'sans-serif'],
      },
      letterSpacing: { broadcast: '0.06em' },
      animation: {
        'fade-in': 'fadeIn 0.25s ease-out forwards',
        'slide-up': 'wipeIn 0.35s cubic-bezier(0.2, 0.9, 0.2, 1) forwards',
        'draw-line': 'drawLine 1.2s ease-out forwards',
        heartbeat: 'heartbeat 1.6s ease-in-out infinite',
        'retract-out': 'retractOut 1.4s ease-in forwards',
        'stamp-in': 'stampIn 0.45s cubic-bezier(0.2, 0.9, 0.2, 1) forwards',
        'score-flash': 'scoreFlash 1.2s ease-out 2',
      },
      keyframes: {
        fadeIn: { '0%': { opacity: '0' }, '100%': { opacity: '1' } },
        wipeIn: {
          '0%': { clipPath: 'inset(0 100% 0 0)', opacity: '0.4' },
          '100%': { clipPath: 'inset(0 0 0 0)', opacity: '1' },
        },
        drawLine: { '0%': { strokeDashoffset: '120' }, '100%': { strokeDashoffset: '0' } },
        retractOut: {
          '0%': { opacity: '1', transform: 'none', filter: 'none' },
          '35%': { opacity: '1', transform: 'none', filter: 'grayscale(1)' },
          '100%': { opacity: '0', transform: 'translateY(6%) scale(0.96)', filter: 'grayscale(1)', visibility: 'hidden' },
        },
        stampIn: {
          '0%': { opacity: '0', transform: 'scale(1.35) rotate(-4deg)' },
          '100%': { opacity: '1', transform: 'scale(1) rotate(-2deg)' },
        },
        scoreFlash: {
          '0%, 100%': { backgroundColor: 'rgba(34,34,30,1)' },
          '40%': { backgroundColor: 'rgba(255,59,47,0.9)' },
        },
        heartbeat: {
          '0%, 100%': { transform: 'scale(1)', opacity: '1' },
          '15%': { transform: 'scale(1.35)', opacity: '0.8' },
          '30%': { transform: 'scale(1)', opacity: '1' },
        },
      },
    },
  },
  plugins: [],
};
