'use client'

import { useTranslations } from 'next-intl'
import { Badge, TBody, TD, TH, THead, TR, Table } from '@/components/ui'
import type { Requirement } from '@/lib/types'

/**
 * What the gap-analysis endpoint can honestly be shown as when no document of
 * the client is sent to it: the requirements of the framework with their
 * articles, each to be checked on the client's documents. The endpoint marks
 * every requirement without evidence as not compliant and computes a score
 * from that; neither is shown, because both would come from missing evidence.
 * Only "not applicable" stays, since it follows from the profile, which was given.
 */
export type ChecklistState = 'toVerify' | 'notApplicable'

export function checklistState(requirement: Pick<Requirement, 'status'>): ChecklistState {
  return requirement.status === 'NOT_APPLICABLE' ? 'notApplicable' : 'toVerify'
}

export function checklistCounts(requirements: Pick<Requirement, 'status'>[]): Record<ChecklistState, number> {
  const counts: Record<ChecklistState, number> = { toVerify: 0, notApplicable: 0 }
  for (const requirement of requirements) counts[checklistState(requirement)] += 1
  return counts
}

export function RequirementsChecklist({ requirements, labelledBy }: { requirements: Requirement[]; labelledBy?: string }) {
  const t = useTranslations('clienti.checklist')
  return (
    <Table aria-labelledby={labelledBy}>
      <THead>
        <TR>
          <TH>{t('colRequirement')}</TH>
          <TH className="hidden sm:table-cell">{t('colArticle')}</TH>
          <TH>{t('colState')}</TH>
        </TR>
      </THead>
      <TBody>
        {requirements.map((req, i) => {
          const state = checklistState(req)
          return (
            <TR key={req.requirement_id || i}>
              <TD className="text-body text-ink">
                {req.description}
                {/* On a phone the article goes under the requirement, so that the state stays in view. */}
                {req.article_reference && <p className="mt-0.5 text-small tabular text-ink-2 sm:hidden">{req.article_reference}</p>}
              </TD>
              <TD className="hidden text-small tabular text-ink-2 sm:table-cell">{req.article_reference || '-'}</TD>
              <TD>
                <Badge tone={state === 'toVerify' ? 'warn' : 'neutral'} className="whitespace-nowrap">
                  {t(`state.${state}`)}
                </Badge>
              </TD>
            </TR>
          )
        })}
      </TBody>
    </Table>
  )
}
