'use client'

import { useTranslations } from 'next-intl'
import type { User } from '@/lib/types'
import { SettingsRow, SettingsSection } from './SettingsSection'

const ROLES: User['role'][] = ['admin', 'member', 'viewer']

/** Who is signed in. Read-only: the backend has no endpoint to update these fields yet. */
export function ProfileSection({ user }: { user: User }) {
  const t = useTranslations('impostazioni.profile')
  const tu = useTranslations('ui')
  const missing = <span className="text-ink-3">{tu('notAvailable')}</span>
  return (
    <SettingsSection id="profilo" title={t('title')} description={t('description')}>
      <dl className="divide-y divide-rule rounded-lg border border-rule bg-surface px-5">
        <SettingsRow label={t('name')}>{user.name || missing}</SettingsRow>
        <SettingsRow label={t('email')}>{user.email}</SettingsRow>
        <SettingsRow label={t('org')}>{user.organization_name || missing}</SettingsRow>
        <SettingsRow label={t('role')}>{ROLES.includes(user.role) ? t(`roles.${user.role}`) : user.role}</SettingsRow>
      </dl>
      <p className="mt-3 max-w-prose text-caption text-ink-3">
        {t.rich('note', {
          mail: (chunks) => (
            <a href="mailto:info@normaai.org" className="text-union underline">
              {chunks}
            </a>
          ),
        })}
      </p>
    </SettingsSection>
  )
}
