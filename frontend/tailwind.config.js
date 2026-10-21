/** @type {import('tailwindcss').Config} */
export default {
  content: ['./index.html', './src/**/*.{js,ts,jsx,tsx}'],
  theme: {
    extend: {
      colors: {
        // PitchPulse palette: night studio, heartbeat pulse, signal cyan.
        pp: {
          night: '#070b14',
          deep: '#0c1222',
          panel: '#111a2e',
          raised: '#18233b',
          line: '#24324f',
          mute: '#8b9bb8',
          pulse: '#ff4d6d',
          pulseSoft: '#ff8fa3',
          signal: '#22d3ee',
          gold: '#fbbf24',
          turf: '#0f2a1d',
          turfLine: '#3c7a57',
        },
      },
      fontFamily: {
        display: ['Oswald', 'Noto Kufi Arabic', 'sans-serif'],
        sans: ['Inter', 'Noto Sans Arabic', 'system-ui', 'sans-serif'],
      },
      animation: {
        'fade-in': 'fadeIn 0.3s ease-out forwards',
        'slide-up': 'slideUp 0.4s cubic-bezier(0.16, 1, 0.3, 1) forwards',
        'draw-line': 'drawLine 1.2s ease-out forwards',
        heartbeat: 'heartbeat 1.6s ease-in-out infinite',
      },
      keyframes: {
        fadeIn: { '0%': { opacity: '0' }, '100%': { opacity: '1' } },
        slideUp: {
          '0%': { transform: 'translateY(16px)', opacity: '0' },
          '100%': { transform: 'translateY(0)', opacity: '1' },
        },
        drawLine: { '0%': { strokeDashoffset: '120' }, '100%': { strokeDashoffset: '0' } },
        heartbeat: {
          '0%, 100%': { transform: 'scale(1)', opacity: '1' },
          '15%': { transform: 'scale(1.25)', opacity: '0.85' },
          '30%': { transform: 'scale(1)', opacity: '1' },
        },
      },
    },
  },
  plugins: [],
};
