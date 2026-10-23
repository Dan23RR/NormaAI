'use client'

import { Badge, Button, FrameworkBadge, TBody, TD, TH, THead, TR, Table } from '@/components/ui'
import { complianceAssessment } from '@/components/clienti/compliance'
import { formatIsoDateTime } from '@/components/clienti/format'
import { REPORT_TYPE_LABEL, type ReportHistoryItem, type ReportType } from './report-api'

function typeLabel(type: string): string {
  return (REPORT_TYPE_LABEL as Record<string, string>)[type] ?? type.replace(/_/g, ' ')
}

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
  return (
    <Table>
      <THead>
        <TR>
          <TH>Data</TH>
          <TH>Cliente</TH>
          <TH>Framework</TH>
          <TH>Valutazione</TH>
          <TH className="hidden md:table-cell">Tipo</TH>
          <TH>
            <span className="sr-only">Azioni</span>
          </TH>
        </TR>
      </THead>
      <TBody>
        {items.map((item) => {
          const frameworks = item.frameworks ?? (item.framework ? [item.framework] : [])
          const assessment = typeof item.overall_score === 'number' ? complianceAssessment(item.overall_score) : null
          return (
            <TR key={item.id}>
              <TD className="whitespace-nowrap tabular text-ink-2">
                {formatIsoDateTime(item.generated_at) ?? <span className="text-ink-3">n.d.</span>}
              </TD>
              <TD className="font-medium">{item.company_name || <span className="text-ink-3">n.d.</span>}</TD>
              <TD>
                {frameworks.length > 0 ? (
                  <div className="flex flex-wrap gap-1">
                    {frameworks.map((fw) => (
                      <FrameworkBadge key={fw} framework={fw} />
                    ))}
                  </div>
                ) : (
                  <span className="text-ink-3">n.d.</span>
                )}
              </TD>
              <TD>
                {assessment ? (
                  <Badge tone={assessment.tone} title={assessment.sublabel}>
                    {assessment.label}
                  </Badge>
                ) : (
                  <span className="text-ink-3">Non registrata</span>
                )}
              </TD>
              <TD className="hidden text-ink-2 md:table-cell">{typeLabel(item.report_type)}</TD>
              <TD className="text-right">
                <Button
                  variant="secondary"
                  size="sm"
                  onClick={() =>
                    onRegenerate({
                      ...item,
                      report_type: (item.report_type in REPORT_TYPE_LABEL ? item.report_type : 'gap_analysis') as ReportType,
                    })
                  }
                >
                  Genera di nuovo
                </Button>
              </TD>
            </TR>
          )
        })}
      </TBody>
    </Table>
  )
}
