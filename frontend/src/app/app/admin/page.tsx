'use client'

import { useEffect, useRef } from 'react'
import { useRouter } from 'next/navigation'
import { useTranslations } from 'next-intl'
import { PageHeader, useToast } from '@/components/ui'
import { useAuth } from '@/hooks/useAuth'
import { InvitesSection } from '@/components/admin/InvitesSection'
import { SystemStatusSection } from '@/components/admin/SystemStatusSection'

function AdminSection({ id, title, description, children }: { id: string; title: string; description?: string; children: React.ReactNode }) {
  return (
    <section id={id} aria-labelledby={`${id}-title`} className="border-t border-rule py-8 first:border-t-0 first:pt-0">
      <h2 id={`${id}-title`} className="text-h3">
        {title}
      </h2>
      {description && <p className="mt-1 max-w-prose text-small text-ink-2">{description}</p>}
      <div className="mt-5">{children}</div>
    </section>
  )
}

/**
 * Administration: invitations and the state of the server. Members are
 * sent back to the start with a notice; there is no user list because the
 * backend has no endpoint that returns one.
 */
export default function AdminPage() {
  const t = useTranslations('admin')
  const { user, demoMode } = useAuth()
  const router = useRouter()
  const { toast } = useToast()
  const redirected = useRef(false)
  const isAdmin = user?.role === 'admin'

  useEffect(() => {
    if (!user || isAdmin || redirected.current) return
    redirected.current = true
    toast({ kind: 'bad', title: t('forbiddenTitle'), description: t('forbiddenDescription') })
    router.replace('/app')
  }, [user, isAdmin, router, toast, t])

  if (!user || !isAdmin) return null

  return (
    <div>
      <PageHeader title={t('title')} description={t('description')} />
      <AdminSection id="inviti" title={t('invites.title')} description={t('invites.description')}>
        <InvitesSection demoMode={demoMode} />
      </AdminSection>
      <AdminSection id="sistema" title={t('system.title')} description={t('system.description')}>
        <SystemStatusSection />
      </AdminSection>
    </div>
  )
}
