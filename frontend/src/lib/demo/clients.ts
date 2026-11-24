/**
 * The clients of the demo firm: five Italian SMEs and one large company, all
 * invented. The names follow the Italian habit of calling example companies
 * Alfa, Beta, Gamma, so that nobody takes them for real ones. Sector, size
 * and turnover are what a consultant would type; the frameworks are the ones
 * that fit each profile:
 *
 * - NIS2 where the sector is in Annex I or II of Directive (EU) 2022/2555
 *   and the company is at least a medium-sized enterprise (Art. 2(1));
 * - CSRD and Taxonomy only for Zeta, the one client above both thresholds
 *   of Art. 19a(1) of Directive 2013/34/EU (more than 1,000 employees and
 *   more than EUR 450 million net turnover);
 * - CRA for the two companies that place products with digital elements on
 *   the market; AI Act where an AI system is provided or used.
 */
export const DEMO_CLIENTS = [
  {
    id: 'demo-c1',
    name: 'Alfa Macchine Utensili S.r.l.',
    sector: 'Macchine utensili a controllo numerico',
    employee_count: 85,
    revenue_eur: 14_000_000,
    jurisdictions: ['IT'],
    applicable_frameworks: ['NIS2', 'CRA', 'GDPR'],
    created_at: '2026-03-09T09:30:00Z',
    updated_at: '2026-11-03T15:10:00Z',
  },
  {
    id: 'demo-c2',
    name: 'Beta Software S.r.l.',
    sector: 'Software gestionale per studi professionali',
    employee_count: 32,
    revenue_eur: 3_800_000,
    jurisdictions: ['IT'],
    applicable_frameworks: ['AI_ACT', 'GDPR', 'CRA'],
    created_at: '2026-03-23T11:00:00Z',
    updated_at: '2026-10-28T10:45:00Z',
  },
  {
    id: 'demo-c3',
    name: 'Gamma Alimentari S.p.A.',
    sector: 'Produzione alimentare',
    employee_count: 140,
    revenue_eur: 38_000_000,
    jurisdictions: ['IT', 'FR'],
    applicable_frameworks: ['NIS2', 'GDPR'],
    created_at: '2026-04-14T14:20:00Z',
    updated_at: '2026-10-19T09:05:00Z',
  },
  {
    id: 'demo-c4',
    name: 'Delta Corriere Espresso S.r.l.',
    sector: 'Servizi di corriere e logistica',
    employee_count: 210,
    revenue_eur: 46_000_000,
    jurisdictions: ['IT'],
    applicable_frameworks: ['NIS2', 'GDPR', 'AI_ACT'],
    created_at: '2026-05-05T08:15:00Z',
    updated_at: '2026-11-05T17:30:00Z',
  },
  {
    id: 'demo-c5',
    name: 'Epsilon Salute S.r.l.',
    sector: 'Poliambulatorio e diagnostica',
    employee_count: 48,
    revenue_eur: 6_500_000,
    jurisdictions: ['IT'],
    applicable_frameworks: ['GDPR', 'AI_ACT'],
    created_at: '2026-06-17T10:00:00Z',
    updated_at: '2026-10-07T12:20:00Z',
  },
  {
    id: 'demo-c6',
    name: 'Zeta Componenti S.p.A.',
    sector: "Componentistica per l'automotive",
    employee_count: 1650,
    revenue_eur: 520_000_000,
    jurisdictions: ['IT', 'DE', 'PL'],
    applicable_frameworks: ['CSRD', 'TAXONOMY', 'NIS2', 'GDPR'],
    created_at: '2026-09-01T09:00:00Z',
    updated_at: '2026-10-26T16:40:00Z',
  },
]
