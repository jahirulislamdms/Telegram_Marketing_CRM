export type Theme = 'dark' | 'light'

export function applyTheme(theme: Theme): void {
  document.documentElement.setAttribute('data-theme', theme)
}
