import type { Locale } from './config'

declare module 'next-intl' {
  interface AppConfig {
    Locale: Locale
  }
}
