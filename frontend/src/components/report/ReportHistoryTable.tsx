'use client'

import { useTranslations } from 'next-intl'
import { Badge, Button, FrameworkBadge, TBody, TD, TH, THead, TR, Table } from '@/components/ui'
import { complianceAssessment } from '@/components/clienti/compliance'
import { formatIsoDateTime } from '@/components/clienti/format'
import { isReportType, reportTypeLabel, type ReportHistoryItem } from './report-api'

/**
 * The reports generated so far. The backend keeps the metadata, not the
 * PDF: the only action is to generate the same report again.
 */
export function ReportHistoryTable({
  items,
  onRegenerate,
}: {
  items: ReportHistoryItem[]
  onRegenerate: (item: ReportHistoryItem) => void
}) {
  const t = useTranslations('report.table')
  const tRoot = useTranslations()
  const missing = <span className="text-ink-3">{tRoot('ui.notAvailable')}</span>
  return (
    <Table>
      <THead>
        <TR>
          <TH>{t('date')}</TH>
          <TH>{t('client')}</TH>
          <TH>{t('framework')}</TH>
          <TH>{t('assessment')}</TH>
          <TH className="hidden md:table-cell">{t('type')}</TH>
          <TH>
            <span className="sr-only">{t('actions')}</span>
          </TH>
        </TR>
      </THead>
      <TBody>
        {items.map((item) => {
          const frameworks = item.frameworks ?? (item.framework ? [item.framework] : [])
          const assessment = typeof item.overall_score === 'number' ? complianceAssessment(item.overall_score, tRoot) : null
          return (
            <TR key={item.id}>
              <TD className="whitespace-nowrap tabular text-ink-2">{formatIsoDateTime(item.generated_at) ?? missing}</TD>
              <TD className="font-medium">{item.company_name || missing}</TD>
              <TD>
                {frameworks.length > 0 ? (
                  <div className="flex flex-wrap gap-1">
                    {frameworks.map((fw) => (
                      <FrameworkBadge key={fw} framework={fw} />
                    ))}
                  </div>
                ) : (
                  missing
                )}
              </TD>
              <TD>
                {assessment ? (
                  <Badge tone={assessment.tone} title={assessment.sublabel}>
                    {assessment.label}
                  </Badge>
                ) : (
                  <span className="text-ink-3">{t('notRecorded')}</span>
                )}
              </TD>
              <TD className="hidden text-ink-2 md:table-cell">{reportTypeLabel(item.report_type, tRoot)}</TD>
              <TD className="text-right">
                <Button
                  variant="secondary"
                  size="sm"
                  onClick={() =>
                    onRegenerate({
                      ...item,
                      report_type: isReportType(item.report_type) ? item.report_type : 'gap_analysis',
                    })
                  }
                >
                  {t('regenerate')}
                </Button>
              </TD>
            </TR>
          )
        })}
      </TBody>
    </Table>
  )
}
