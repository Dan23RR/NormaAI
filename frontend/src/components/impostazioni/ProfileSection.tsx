'use client'

import type { User } from '@/lib/types'
import { SettingsRow, SettingsSection } from './SettingsSection'

const ROLE_LABEL: Record<User['role'], string> = {
  admin: 'Amministratore',
  member: 'Membro',
  viewer: 'Lettore',
}

/** Who is signed in. Read-only: the backend has no endpoint to update these fields yet. */
export function ProfileSection({ user }: { user: User }) {
  return (
    <SettingsSection id="profilo" title="Profilo" description="L’account con cui sei entrato e la sua organizzazione.">
      <dl className="divide-y divide-rule rounded-lg border border-rule bg-surface px-5">
        <SettingsRow label="Nome">{user.name || <span className="text-ink-3">n.d.</span>}</SettingsRow>
        <SettingsRow label="Email">{user.email}</SettingsRow>
        <SettingsRow label="Organizzazione">{user.organization_name || <span className="text-ink-3">n.d.</span>}</SettingsRow>
        <SettingsRow label="Ruolo">{ROLE_LABEL[user.role] ?? user.role}</SettingsRow>
      </dl>
      <p className="mt-3 max-w-prose text-caption text-ink-3">
        Nome, email e organizzazione non si modificano ancora da qui: il server non ha un endpoint per aggiornarli. Per
        cambiarli scrivi a{' '}
        <a href="mailto:info@normaai.org" className="text-union underline">
          info@normaai.org
        </a>
        .
      </p>
    </SettingsSection>
  )
}
