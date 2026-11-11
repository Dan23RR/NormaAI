import { APP_NAV } from '@/components/app/AppShell'

/** Where the demo opens while the document check has no screen in the build. */
export const DEMO_HOME = '/app'
/** The screen of the document check: the demo opens there as soon as the build has it. */
export const DEMO_DOCUMENT_CHECK = '/app/controlla'

/**
 * The first page of the demo.
 *
 * The navigation of the application lists the surfaces a build ships, so the
 * document check is the destination exactly when it is listed there. A test
 * pins that list to the files in src/app/app, so the two cannot drift apart.
 * Client code only: APP_NAV lives in a client module.
 */
export function demoDestination(nav: ReadonlyArray<{ href: string }> = APP_NAV): string {
  return nav.some((item) => item.href === DEMO_DOCUMENT_CHECK) ? DEMO_DOCUMENT_CHECK : DEMO_HOME
}
