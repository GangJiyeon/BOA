// Tools for local development are hidden unless explicitly enabled.
const env = import.meta.env
export const showDevTools = env?.DEV === true && env.VITE_SHOW_DEV_TOOLS === 'true'
export const emailLoginEnabled = showDevTools || env?.VITE_EMAIL_LOGIN_ENABLED === 'true'
