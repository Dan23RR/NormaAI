'use client'

import { useEffect, useState } from 'react'
import { useTranslations } from 'next-intl'
import { Checkbox } from '@/components/ui/Field'
import { useToast } from '@/components/ui/Toast'
import { fetchPreferences, savePreferences } from './documents-api'
import { describeFailure } from './errors'

/**
 * Whether the email digest of the documents to review is wanted. The switch
 * appears once the server has said what the preference is: when it cannot,
 * nothing is shown rather than a box that might not match the truth.
 */
export function EmailDigestToggle({ demo, className }: { demo: boolean; className?: string }) {
  const t = useTranslations('controlla')
  const { toast } = useToast()
  const [on, setOn] = useState<boolean | null>(null)
  const [saving, setSaving] = useState(false)

  useEffect(() => {
    let alive = true
    fetchPreferences()
      .then((preferences) => {
        if (alive) setOn(preferences.email_digest)
      })
      .catch(() => {
        /* the preference stays out of the page */
      })
    return () => {
      alive = false
    }
  }, [])

  if (on === null) return null

  const change = async (next: boolean) => {
    const previous = on
    setOn(next)
    setSaving(true)
    try {
      const saved = await savePreferences({ email_digest: next })
      setOn(saved.email_digest)
      toast({ kind: 'ok', title: t('digest.savedTitle'), description: saved.email_digest ? t('digest.on') : t('digest.off') })
    } catch (err) {
      setOn(previous)
      toast({ kind: 'bad', title: t('digest.failedTitle'), description: t(`errors.${describeFailure(err).kind}`) })
    } finally {
      setSaving(false)
    }
  }

  return (
    <Checkbox
      id="controlla-email-digest"
      className={className}
      checked={on}
      disabled={saving}
      onChange={(event) => void change(event.target.checked)}
      label={<span className="text-small">{t('digest.label')}</span>}
      // On the page background the helper text needs the darker of the two greys.
      description={<span className="text-ink-2">{demo ? t('demo.digest') : t('digest.help')}</span>}
    />
  )
}
