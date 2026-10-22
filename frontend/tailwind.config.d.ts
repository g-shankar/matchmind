// Types for the parts of the Tailwind config that the contrast tests read.
declare const config: {
  theme: { extend: { colors: { pp: Record<string, string> } } };
};
export default config;
