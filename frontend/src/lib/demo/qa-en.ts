/**
 * Demo answers of "Chiedi", English: the same scenarios as qa-it.ts, with the
 * same citations in the same order. Every passage marked `verified: true` is
 * the official English text, word for word, in the version named in acts.ts
 * (scripts/check_demo_quotes.py checks this file against the English texts).
 */
import type { DemoCitation, DemoQAResponse, DemoQAScenario } from './types'

const AI_ACT_ART50_QUOTE =
  'Providers shall ensure that AI systems intended to interact directly with natural persons are designed and developed in such a way that the natural persons concerned are informed that they are interacting with an AI system'

const AI_ACT_ART9_QUOTE =
  'A risk management system shall be established, implemented, documented and maintained in relation to high-risk AI systems.'

const AI_ACT_ART113_QUOTE =
  'It shall apply from 2 August 2026.'

const AI_ACT_ART113_ANNEX3_QUOTE =
  '2 December 2027 as regards AI systems classified as high-risk pursuant to Article 6(2) and Annex III'

const AI_ACT_ART99_SME_QUOTE =
  'In the case of SMEs, including start-ups, each fine referred to in this Article shall be up to the percentages or amount referred to in paragraphs 3, 4 and 5, whichever thereof is lower.'

const ACCOUNTING_ART19A_SCOPE_QUOTE =
  "Undertakings which, on their balance sheet dates, exceed a net turnover of EUR 450 000 000 and an average number of 1 000 employees during the financial year shall include in their management report information necessary to understand the undertaking's impacts on sustainability matters"

const ACCOUNTING_ART19A_PROTECTED_QUOTE =
  'Protected undertakings shall have the right to decline to provide information exceeding the information specified in the voluntary standards'

const CSDDD_ART5_QUOTE =
  "Member States shall ensure that companies conduct risk-based human rights and environmental due diligence as laid down in Articles 7 to 16 ('due diligence')"

const CSDDD_ART8_PARTNERS_QUOTE =
  'companies may request information from business partners only where that information is necessary, and, in the case of business partners with fewer than 5 000 employees, only when the information cannot reasonably be obtained by other means'

const DORA_ART6_QUOTE =
  'Financial entities shall have a sound, comprehensive and well-documented ICT risk management framework as part of their overall risk management system'

const DORA_ART19_QUOTE =
  'Financial entities shall report major ICT-related incidents to the relevant competent authority as referred to in Article 46'

const DORA_ART28_QUOTE =
  'Financial entities shall manage ICT third-party risk as an integral component of ICT risk within their ICT risk management framework'

const NIS2_ART23_4A_QUOTE =
  'without undue delay and in any event within 24 hours of becoming aware of the significant incident, an early warning'

const GDPR_ART37_QUOTE =
  'The controller and the processor shall designate a data protection officer in any case where'

/** The voluntary standard of July 2026 is not one of the acts of the corpus: cited, not verified. */
const VOLUNTARY_STANDARD: DemoCitation = {
  framework: 'CSRD',
  title: 'Delegated Regulation (EU) 2026/1560',
  reference: 'Art. 3 and Annex II (value-chain cap)',
  quote_snippet: '',
  celex: '32026R1560',
  verified: false,
}

const VOLUNTARY_STANDARD_CAVEAT =
  'Delegated Regulation (EU) 2026/1560 on the voluntary standards is not one of the acts of the corpus: the citation to it still has to be checked on EUR-Lex.'

const ITALIAN_LAW_CAVEAT =
  'Italian national law is not in the corpus of Chiedi yet: the citation to it still has to be checked on Normattiva.'

export const QA_EN: Record<DemoQAScenario, DemoQAResponse> = {
  csrd: {
    answer:
      'After Omnibus I (Directive (EU) 2026/470, in force since 18 March 2026) sustainability reporting is mandatory only for undertakings that exceed both thresholds: a net turnover above EUR 450 million and more than 1,000 employees on average during the financial year [1]. The conditions are cumulative: a company with 600 employees stays outside the obligation, whatever its turnover. The new scope applies to financial years starting on or after 1 January 2027 [2]; for financial years 2025 and 2026 Member States may exempt first-wave undertakings that do not exceed the new thresholds [3].\n\nA company below the thresholds can still receive data requests from a customer that has to report. The directive protects undertakings with up to 1,000 employees that are in the value chain of a reporting undertaking: they have the right to decline information that goes beyond the voluntary standards [4], set by Delegated Regulation (EU) 2026/1560 [5].\n\nIn Italy the CSRD is transposed by Legislative Decree 125/2024. Decree-Law No 193 of 23 October 2026 excluded from the decree, for financial years starting in 2026 and 2027, undertakings with a net turnover not above EUR 450 million or with no more than 1,000 employees [6]. The amendments to the directive must be transposed by 19 March 2027 [7].',
    citations: [
      {
        framework: 'CSRD',
        reference: 'Art. 19a(1) of Directive 2013/34/EU',
        quote_snippet: ACCOUNTING_ART19A_SCOPE_QUOTE,
        celex: '32013L0034',
        verified: true,
      },
      {
        framework: 'CSRD',
        reference: 'Art. 5(2), first subparagraph, point (b)',
        quote_snippet: 'for financial years starting on or after 1 January 2027',
        celex: '32022L2464',
        verified: true,
      },
      {
        framework: 'CSRD',
        reference: 'Art. 5(2), last subparagraph',
        quote_snippet:
          'Member States may exempt undertakings or issuers which do not exceed a net turnover of EUR 450 000 000 or an average number of 1 000 employees during the financial year, on a consolidated basis where applicable',
        celex: '32022L2464',
        verified: true,
      },
      {
        framework: 'CSRD',
        reference: 'Art. 19a(3) of Directive 2013/34/EU',
        quote_snippet: ACCOUNTING_ART19A_PROTECTED_QUOTE,
        celex: '32013L0034',
        verified: true,
      },
      VOLUNTARY_STANDARD,
      {
        framework: 'IT',
        title: 'Decree-Law No 193 of 23 October 2026',
        reference: 'Art. 10 (new paragraph 3-bis of Art. 17 of Legislative Decree 125/2024)',
        quote_snippet: '',
        url: 'https://www.normattiva.it/uri-res/N2Ls?urn:nir:stato:decreto.legge:2026-10-23;193',
        verified: false,
      },
      {
        framework: 'CSRD',
        title: 'Directive (EU) 2026/470 (Omnibus I)',
        reference: 'Art. 5(1)',
        quote_snippet:
          'Member States shall bring into force the laws, regulations and administrative provisions necessary to comply with Articles 1, 2 and 3 by 19 March 2027.',
        celex: '32026L0470',
        verified: true,
      },
    ],
    confidence_score: 0.86,
    requires_expert_review: true,
    related_frameworks: ['CSDDD', 'TAXONOMY'],
    caveats: [
      VOLUNTARY_STANDARD_CAVEAT,
      ITALIAN_LAW_CAVEAT,
      'Decree-Law 193/2026 has to be converted into law within sixty days of its publication, and its text may change.',
    ],
  },
  csddd: {
    answer:
      'The CSDDD (Directive (EU) 2024/1760) requires the largest companies to carry out human rights and environmental due diligence along their chain of activities: integrate it into their policies, identify and assess adverse impacts, prevent them or bring them to an end, and report on it [1]. After Omnibus I (Directive (EU) 2026/470) it covers companies with more than 5,000 employees on average and a net worldwide turnover above EUR 1.5 billion [2]: an SME has no direct obligations.\n\nThe timeline was rewritten: Member States transpose by 26 July 2028 [3] and the rules apply from 26 July 2029 [4]. The same act deleted Article 22 on the climate transition plan and the first paragraph of Article 29, which harmonised civil liability.\n\nFor a supplier one new limit matters most: in-scope companies may ask business partners for information only where it is necessary and, when the partner has fewer than 5,000 employees, only when they cannot reasonably obtain it by other means [5]. In-scope companies must also accept complaints from anyone with legitimate concerns about an adverse impact [6].',
    citations: [
      {
        framework: 'CSDDD',
        reference: 'Art. 5(1)',
        quote_snippet: CSDDD_ART5_QUOTE,
        celex: '32024L1760',
        verified: true,
      },
      {
        framework: 'CSDDD',
        reference: 'Art. 2(1), point (a)',
        quote_snippet:
          'the company had more than 5 000 employees on average and had a net worldwide turnover of more than EUR 1 500 000 000 in the last financial year for which annual financial statements have been or should have been adopted',
        celex: '32024L1760',
        verified: true,
      },
      {
        framework: 'CSDDD',
        reference: 'Art. 37(1), first subparagraph',
        quote_snippet:
          'Member States shall adopt and publish, by 26 July 2028, the laws, regulations and administrative provisions necessary to comply with this Directive.',
        celex: '32024L1760',
        verified: true,
      },
      {
        framework: 'CSDDD',
        reference: 'Art. 37(1), second subparagraph',
        quote_snippet: 'They shall apply those measures from 26 July 2029',
        celex: '32024L1760',
        verified: true,
      },
      {
        framework: 'CSDDD',
        reference: 'Art. 8(2a), point (a)',
        quote_snippet: CSDDD_ART8_PARTNERS_QUOTE,
        celex: '32024L1760',
        verified: true,
      },
      {
        framework: 'CSDDD',
        reference: 'Art. 14(1)',
        quote_snippet:
          'enable persons and entities listed in paragraph 2 to submit complaints to them where those persons or entities have legitimate concerns regarding actual or potential adverse impacts',
        celex: '32024L1760',
        verified: true,
      },
    ],
    confidence_score: 0.9,
    requires_expert_review: false,
    related_frameworks: ['CSRD'],
    caveats: ['The national transposition rules, due by 26 July 2028, may specify obligations and penalties.'],
  },
  value_chain: {
    answer:
      "It depends on why the customer is asking. If the customer collects data for its own sustainability reporting and your company does not exceed 1,000 employees, you are a 'protected undertaking' [1]: you have the right to decline information that goes beyond the voluntary standards [2], and a contract clause requiring it is not binding [3]. The customer must also tell you which requests go beyond that limit and that you may decline them. The voluntary standards and the list of the information covered by the limit are in Delegated Regulation (EU) 2026/1560 [4]; the limit applies from financial years starting on or after 1 January 2027.\n\nIf the customer is instead a company subject to the CSDDD and contacts you for its own due diligence, another rule applies: it may ask for information only where necessary and, from a partner with fewer than 5,000 employees, only when it cannot reasonably obtain it by other means [5].\n\nThe reporting limit does not cover requests made for other purposes, for example those of a bank deciding on a loan: the regulation only encourages banks and insurers to stay within the perimeter of the voluntary standards.",
    citations: [
      {
        framework: 'CSRD',
        reference: 'Art. 19a(3) of Directive 2013/34/EU (definition of protected undertaking)',
        quote_snippet:
          'does not exceed, on its balance sheet date, an average number of 1 000 employees during the preceding financial year',
        celex: '32013L0034',
        verified: true,
      },
      {
        framework: 'CSRD',
        reference: 'Art. 19a(3) of Directive 2013/34/EU',
        quote_snippet: ACCOUNTING_ART19A_PROTECTED_QUOTE,
        celex: '32013L0034',
        verified: true,
      },
      {
        framework: 'CSRD',
        reference: 'Art. 19a(3), fourth subparagraph, point (b), of Directive 2013/34/EU',
        quote_snippet: 'any contractual provision contrary to point (a) shall not be binding',
        celex: '32013L0034',
        verified: true,
      },
      VOLUNTARY_STANDARD,
      {
        framework: 'CSDDD',
        reference: 'Art. 8(2a), point (a)',
        quote_snippet: CSDDD_ART8_PARTNERS_QUOTE,
        celex: '32024L1760',
        verified: true,
      },
    ],
    confidence_score: 0.87,
    requires_expert_review: false,
    related_frameworks: ['CSRD', 'CSDDD'],
    caveats: [VOLUNTARY_STANDARD_CAVEAT],
  },
  ai_act: {
    answer:
      'Regulation (EU) 2024/1689 (the AI Act) scales obligations to risk. Some practices are prohibited, for example systems that use subliminal or manipulative techniques to distort the behaviour of people [1]. The systems listed in Annex III are high-risk [2], including those used to recruit staff [3] or to assess creditworthiness, and so are the systems that are safety components of regulated products: for these a risk management system is established [4], with data governance, technical documentation, transparency and human oversight.\n\nThe regulation applies from 2 August 2026 [5], but Regulation (EU) 2026/1744 moved the high-risk dates: 2 December 2027 for the systems of Annex III [6] and 2 August 2028 for those linked to the products of Annex I [7]. The transparency obligations of Article 50 (virtual assistants, synthetic content) already apply from 2 August 2026.\n\nFines for prohibited practices go up to EUR 35 million or 7% of total worldwide annual turnover, whichever is higher [8]; for SMEs the lower of the two amounts applies [9].',
    citations: [
      {
        framework: 'AI_ACT',
        reference: 'Art. 5(1), point (a)',
        quote_snippet:
          "the placing on the market, the putting into service or the use of an AI system that deploys subliminal techniques beyond a person's consciousness or purposefully manipulative or deceptive techniques",
        celex: '32024R1689',
        verified: true,
      },
      {
        framework: 'AI_ACT',
        reference: 'Art. 6(2)',
        quote_snippet:
          'In addition to the high-risk AI systems referred to in paragraph 1, AI systems referred to in Annex III shall be considered to be high-risk.',
        celex: '32024R1689',
        verified: true,
      },
      {
        framework: 'AI_ACT',
        reference: 'Annex III, point 4(a)',
        quote_snippet:
          'AI systems intended to be used for the recruitment or selection of natural persons, in particular to place targeted job advertisements, to analyse and filter job applications, and to evaluate candidates',
        celex: '32024R1689',
        verified: true,
      },
      {
        framework: 'AI_ACT',
        reference: 'Art. 9(1)',
        quote_snippet: AI_ACT_ART9_QUOTE,
        celex: '32024R1689',
        verified: true,
      },
      {
        framework: 'AI_ACT',
        reference: 'Art. 113, second paragraph',
        quote_snippet: AI_ACT_ART113_QUOTE,
        celex: '32024R1689',
        verified: true,
      },
      {
        framework: 'AI_ACT',
        reference: 'Art. 113, third paragraph, point (c)(i)',
        quote_snippet: AI_ACT_ART113_ANNEX3_QUOTE,
        celex: '32024R1689',
        verified: true,
      },
      {
        framework: 'AI_ACT',
        reference: 'Art. 113, third paragraph, point (c)(ii)',
        quote_snippet: '2 August 2028 as regards AI systems classified as high-risk pursuant to Article 6(1) and Annex I',
        celex: '32024R1689',
        verified: true,
      },
      {
        framework: 'AI_ACT',
        reference: 'Art. 99(3)',
        quote_snippet:
          'Non-compliance with the prohibition of the AI practices referred to in Article 5 shall be subject to administrative fines of up to EUR 35 000 000 or, if the offender is an undertaking, up to 7 % of its total worldwide annual turnover for the preceding financial year, whichever is higher.',
        celex: '32024R1689',
        verified: true,
      },
      {
        framework: 'AI_ACT',
        reference: 'Art. 99(6)',
        quote_snippet: AI_ACT_ART99_SME_QUOTE,
        celex: '32024R1689',
        verified: true,
      },
    ],
    confidence_score: 0.93,
    requires_expert_review: false,
    related_frameworks: ['GDPR'],
    caveats: [
      'Whether a system is high-risk depends on its actual use: Article 6(3) excludes Annex III systems that do not pose a significant risk.',
    ],
  },
  ai_act_art50: {
    answer:
      'Yes. Article 50(1) of Regulation (EU) 2024/1689 requires whoever provides an AI system intended to interact directly with people to design it so that people know they are talking to an AI, unless this is obvious to a reasonably well-informed, observant and circumspect person [1]. The information must be given in a clear and distinguishable manner at the latest at the first interaction [2]: for an assistant on the company website an explicit statement at the start of the conversation is enough. The design obligation lies with the provider of the system; the company that puts it on its own website is well advised to check that the notice is there.\n\nThe obligation applies from 2 August 2026 [3]. If the assistant generates text, audio or images, the provider must also mark the outputs as artificially generated [4]; for systems already on the market before 2 August 2026 the deadline to comply is 2 December 2026 [5].\n\nA breach of the transparency obligations is punished with fines of up to EUR 15 million or 3% of total worldwide annual turnover, whichever is higher [6]; for SMEs and start-ups the lower of the two amounts applies [7].',
    citations: [
      {
        framework: 'AI_ACT',
        reference: 'Art. 50(1)',
        quote_snippet: AI_ACT_ART50_QUOTE,
        celex: '32024R1689',
        verified: true,
      },
      {
        framework: 'AI_ACT',
        reference: 'Art. 50(5)',
        quote_snippet:
          'The information referred to in paragraphs 1 to 4 shall be provided to the natural persons concerned in a clear and distinguishable manner at the latest at the time of the first interaction or exposure.',
        celex: '32024R1689',
        verified: true,
      },
      {
        framework: 'AI_ACT',
        reference: 'Art. 113, second paragraph',
        quote_snippet: AI_ACT_ART113_QUOTE,
        celex: '32024R1689',
        verified: true,
      },
      {
        framework: 'AI_ACT',
        reference: 'Art. 50(2)',
        quote_snippet:
          'shall ensure that the outputs of the AI system are marked in a machine-readable format and detectable as artificially generated or manipulated',
        celex: '32024R1689',
        verified: true,
      },
      {
        framework: 'AI_ACT',
        reference: 'Art. 111(4)',
        quote_snippet:
          'that have been placed on the market before 2 August 2026 shall take the necessary steps in order to comply with Article 50(2) by 2 December 2026',
        celex: '32024R1689',
        verified: true,
      },
      {
        framework: 'AI_ACT',
        reference: 'Art. 99(4)',
        quote_snippet:
          'shall be subject to administrative fines of up to EUR 15 000 000 or, if the offender is an undertaking, up to 3 % of its total worldwide annual turnover for the preceding financial year, whichever is higher',
        celex: '32024R1689',
        verified: true,
      },
      {
        framework: 'AI_ACT',
        reference: 'Art. 99(6)',
        quote_snippet: AI_ACT_ART99_SME_QUOTE,
        celex: '32024R1689',
        verified: true,
      },
    ],
    confidence_score: 0.94,
    requires_expert_review: false,
    related_frameworks: ['GDPR'],
    caveats: [],
  },
  ai_act_art4: {
    answer:
      'Article 4 of the AI Act, in the text replaced by Regulation (EU) 2026/1744, asks providers and deployers (whoever uses an AI system in their own activity) to take measures that support the AI literacy of their staff and of those who use the systems on their behalf, taking into account knowledge, experience and the context of use [1]. There is no level to reach and no certificate to obtain: the obligation does not require anyone to guarantee a specific level of AI literacy of any individual [2].\n\nIn practice it is sensible to know which AI systems are in use, to give the people who use them proportionate instructions (what they do, what their limits are, when a human check is needed) and to keep a record of what was done. The Commission and the Member States must support undertakings, SMEs in particular [3], and the Commission publishes practical examples of how to comply.',
    citations: [
      {
        framework: 'AI_ACT',
        reference: 'Art. 4(1)',
        quote_snippet:
          'Providers and deployers of AI systems shall take measures to support the development of AI literacy of their staff and other persons dealing with the operation and use of AI systems on their behalf',
        celex: '32024R1689',
        verified: true,
      },
      {
        framework: 'AI_ACT',
        reference: 'Art. 4(1), last sentence',
        quote_snippet:
          'This obligation does not require providers or deployers to guarantee any specific level of AI literacy of any individual.',
        celex: '32024R1689',
        verified: true,
      },
      {
        framework: 'AI_ACT',
        reference: 'Art. 4(2)',
        quote_snippet:
          'The Commission and the Member States shall support and facilitate the efforts of providers and deployers of AI systems, in particular SMEs, in fulfilling their obligation under paragraph 1 of this Article.',
        celex: '32024R1689',
        verified: true,
      },
    ],
    confidence_score: 0.93,
    requires_expert_review: false,
    related_frameworks: ['GDPR'],
    caveats: ['The text of Article 4 is the one in force since 27 July 2026: guides written before that date describe a different obligation.'],
  },
  ai_act_art9: {
    answer:
      'Article 9 of the AI Act requires, for high-risk AI systems, a risk management system that is established, implemented, documented and maintained [1]. It is not a one-off task: it is a continuous iterative process, planned and run throughout the entire lifecycle of the system, with regular systematic review and updating [2].\n\nThe process covers the identification and analysis of the known and reasonably foreseeable risks to health, safety and fundamental rights, the estimation of the risks of intended use and of reasonably foreseeable misuse, and the adoption of appropriate measures. The systems are tested to identify the most appropriate risk management measures [3]. For the systems of Annex III these requirements apply from 2 December 2027 [4].',
    citations: [
      {
        framework: 'AI_ACT',
        reference: 'Art. 9(1)',
        quote_snippet: AI_ACT_ART9_QUOTE,
        celex: '32024R1689',
        verified: true,
      },
      {
        framework: 'AI_ACT',
        reference: 'Art. 9(2)',
        quote_snippet:
          'The risk management system shall be understood as a continuous iterative process planned and run throughout the entire lifecycle of a high-risk AI system, requiring regular systematic review and updating.',
        celex: '32024R1689',
        verified: true,
      },
      {
        framework: 'AI_ACT',
        reference: 'Art. 9(6)',
        quote_snippet:
          'High-risk AI systems shall be tested for the purpose of identifying the most appropriate and targeted risk management measures.',
        celex: '32024R1689',
        verified: true,
      },
      {
        framework: 'AI_ACT',
        reference: 'Art. 113, third paragraph, point (c)(i)',
        quote_snippet: AI_ACT_ART113_ANNEX3_QUOTE,
        celex: '32024R1689',
        verified: true,
      },
    ],
    confidence_score: 0.93,
    requires_expert_review: false,
    related_frameworks: ['GDPR'],
    caveats: ['Harmonised standards will specify how to implement it.'],
  },
  gdpr: {
    answer:
      'Regulation (EU) 2016/679 (GDPR) sets the principles for processing personal data. Processing is lawful only if at least one legal basis applies: consent, contract, legal obligation, vital interests, public interest or legitimate interests [1]. Data must be adequate, relevant and limited to what is necessary for the purposes [2].\n\nData subjects have the rights of access, rectification, erasure, restriction, portability and objection (Articles 15 to 21). In the case of a personal data breach, the controller notifies the supervisory authority without undue delay and, where feasible, within 72 hours [3]. Designating a data protection officer is mandatory, among other cases, for public authorities and bodies and when the core activities involve regular and systematic monitoring on a large scale [4].\n\nFines for the most serious infringements go up to EUR 20 million or 4% of total worldwide annual turnover, whichever is higher [5].',
    citations: [
      {
        framework: 'GDPR',
        reference: 'Art. 6(1)',
        quote_snippet: 'Processing shall be lawful only if and to the extent that at least one of the following applies',
        celex: '32016R0679',
        verified: true,
      },
      {
        framework: 'GDPR',
        reference: 'Art. 5(1), point (c)',
        quote_snippet:
          "adequate, relevant and limited to what is necessary in relation to the purposes for which they are processed ('data minimisation')",
        celex: '32016R0679',
        verified: true,
      },
      {
        framework: 'GDPR',
        reference: 'Art. 33(1)',
        quote_snippet:
          'the controller shall without undue delay and, where feasible, not later than 72 hours after having become aware of it, notify the personal data breach to the supervisory authority competent in accordance with Article 55',
        celex: '32016R0679',
        verified: true,
      },
      {
        framework: 'GDPR',
        reference: 'Art. 37(1)',
        quote_snippet: GDPR_ART37_QUOTE,
        celex: '32016R0679',
        verified: true,
      },
      {
        framework: 'GDPR',
        reference: 'Art. 83(5)',
        quote_snippet:
          'up to 20 000 000 EUR, or in the case of an undertaking, up to 4 % of the total worldwide annual turnover of the preceding financial year, whichever is higher',
        celex: '32016R0679',
        verified: true,
      },
    ],
    confidence_score: 0.94,
    requires_expert_review: false,
    related_frameworks: ['AI_ACT', 'NIS2'],
    caveats: [],
  },
  gdpr_art9: {
    answer:
      "Article 9 of the GDPR prohibits the processing of personal data revealing racial or ethnic origin, political opinions, religious or philosophical beliefs or trade union membership, and the processing of genetic data, biometric data for the purpose of uniquely identifying a person, data concerning health or a person's sex life or sexual orientation [1].\n\nThe prohibition falls only in the cases listed in paragraph 2, including the explicit consent of the data subject for specified purposes [2], obligations in the field of employment and social security law, vital interests, data manifestly made public, the defence of legal claims, reasons of substantial public interest and the purposes of medicine, public health, archiving and research.\n\nMember States may introduce further conditions, including limitations, for genetic data, biometric data and data concerning health [3].",
    citations: [
      {
        framework: 'GDPR',
        reference: 'Art. 9(1)',
        quote_snippet:
          "Processing of personal data revealing racial or ethnic origin, political opinions, religious or philosophical beliefs, or trade union membership, and the processing of genetic data, biometric data for the purpose of uniquely identifying a natural person, data concerning health or data concerning a natural person's sex life or sexual orientation shall be prohibited.",
        celex: '32016R0679',
        verified: true,
      },
      {
        framework: 'GDPR',
        reference: 'Art. 9(2), point (a)',
        quote_snippet:
          'the data subject has given explicit consent to the processing of those personal data for one or more specified purposes',
        celex: '32016R0679',
        verified: true,
      },
      {
        framework: 'GDPR',
        reference: 'Art. 9(4)',
        quote_snippet:
          'Member States may maintain or introduce further conditions, including limitations, with regard to the processing of genetic data, biometric data or data concerning health.',
        celex: '32016R0679',
        verified: true,
      },
    ],
    confidence_score: 0.95,
    requires_expert_review: false,
    related_frameworks: ['AI_ACT'],
    caveats: ['The exceptions of paragraph 2 have to be assessed case by case, with the data protection officer.'],
  },
  gdpr_art13: {
    answer:
      'Article 13 of the GDPR lists the information the controller gives the data subject at the time the data are collected directly from him or her [1]: identity and contact details of the controller and of the data protection officer, purposes and legal basis, recipients, any transfer to third countries. To these is added the information necessary for fair and transparent processing [2]: storage period, rights of the data subject, right to lodge a complaint with the supervisory authority and, where automated decision-making exists, the logic involved and the envisaged consequences.\n\nThe notice must be given in a concise, transparent, intelligible and easily accessible form, using clear and plain language [3].',
    citations: [
      {
        framework: 'GDPR',
        reference: 'Art. 13(1)',
        quote_snippet:
          'Where personal data relating to a data subject are collected from the data subject, the controller shall, at the time when personal data are obtained, provide the data subject with all of the following information',
        celex: '32016R0679',
        verified: true,
      },
      {
        framework: 'GDPR',
        reference: 'Art. 13(2)',
        quote_snippet:
          'provide the data subject with the following further information necessary to ensure fair and transparent processing',
        celex: '32016R0679',
        verified: true,
      },
      {
        framework: 'GDPR',
        reference: 'Art. 12(1)',
        quote_snippet: 'in a concise, transparent, intelligible and easily accessible form, using clear and plain language',
        celex: '32016R0679',
        verified: true,
      },
    ],
    confidence_score: 0.95,
    requires_expert_review: false,
    related_frameworks: ['AI_ACT'],
    caveats: [],
  },
  gdpr_art17: {
    answer:
      'Article 17 of the GDPR gives the data subject the right to obtain from the controller the erasure of personal data concerning him or her without undue delay [1], where one of the grounds applies:\n\n1. the data are no longer necessary for the purposes for which they were collected;\n2. the data subject withdraws consent and there is no other legal ground;\n3. the data subject objects to the processing and there are no overriding legitimate grounds;\n4. the data have been unlawfully processed;\n5. erasure is required by a legal obligation in Union or Member State law.\n\nWhere the controller has made the data public, it takes reasonable steps to inform the other controllers processing them of the erasure request [2]. The right does not apply where processing is necessary for exercising the right of freedom of expression and information, for compliance with a legal obligation, for reasons of public interest in the area of public health, for archiving or research purposes, or for the establishment, exercise or defence of legal claims [3].',
    citations: [
      {
        framework: 'GDPR',
        reference: 'Art. 17(1)',
        quote_snippet:
          'The data subject shall have the right to obtain from the controller the erasure of personal data concerning him or her without undue delay',
        celex: '32016R0679',
        verified: true,
      },
      {
        framework: 'GDPR',
        reference: 'Art. 17(2)',
        quote_snippet:
          'shall take reasonable steps, including technical measures, to inform controllers which are processing the personal data that the data subject has requested the erasure by such controllers of any links to, or copy or replication of, those personal data',
        celex: '32016R0679',
        verified: true,
      },
      {
        framework: 'GDPR',
        reference: 'Art. 17(3), point (a)',
        quote_snippet:
          'Paragraphs 1 and 2 shall not apply to the extent that processing is necessary: (a) for exercising the right of freedom of expression and information',
        celex: '32016R0679',
        verified: true,
      },
    ],
    confidence_score: 0.95,
    requires_expert_review: false,
    related_frameworks: ['AI_ACT'],
    caveats: ['The exceptions of paragraph 3 have to be assessed case by case, with the data protection officer.'],
  },
  gdpr_dpo: {
    answer:
      'A data protection officer (DPO) must be designated in any case [1] where the processing is carried out by a public authority or body, where the core activities require regular and systematic monitoring of data subjects on a large scale, or where they consist of processing on a large scale of special categories of data or of data relating to criminal convictions.\n\nThe DPO is independent: he or she receives no instructions on the exercise of the tasks and may not be dismissed or penalised for performing them [2]; the DPO reports to the highest management level of the controller. The tasks include informing and advising the controller and the employees of their data protection obligations [3], monitoring compliance with the regulation, advising on the impact assessment and acting as the contact point for the supervisory authority.',
    citations: [
      {
        framework: 'GDPR',
        reference: 'Art. 37(1)',
        quote_snippet: GDPR_ART37_QUOTE,
        celex: '32016R0679',
        verified: true,
      },
      {
        framework: 'GDPR',
        reference: 'Art. 38(3)',
        quote_snippet: 'He or she shall not be dismissed or penalised by the controller or the processor for performing his tasks.',
        celex: '32016R0679',
        verified: true,
      },
      {
        framework: 'GDPR',
        reference: 'Art. 39(1), point (a)',
        quote_snippet:
          'to inform and advise the controller or the processor and the employees who carry out processing of their obligations pursuant to this Regulation',
        celex: '32016R0679',
        verified: true,
      },
    ],
    confidence_score: 0.95,
    requires_expert_review: false,
    related_frameworks: ['NIS2', 'AI_ACT'],
    caveats: ["The regulation does not define 'large scale': the assessment has to be made on the actual case."],
  },
  dora: {
    answer:
      'Regulation (EU) 2022/2554 (DORA) applies from 17 January 2025 [1] and requires financial entities to have a sound, comprehensive and documented ICT risk management framework [2]. Major ICT-related incidents must be reported to the competent authority [3] with an initial notification, an intermediate report and a final report, within the time limits set by the regulatory technical standards.\n\nThe entities identified by the competent authorities, other than microenterprises and those under the simplified framework, carry out threat-led penetration testing (TLPT) at least every three years [4]. The risk arising from ICT third-party service providers must be managed as an integral part of ICT risk [5], with the minimum contractual content of Article 30: this is where the requests of banks and insurers to their software and service suppliers come from.',
    citations: [
      {
        framework: 'DORA',
        reference: 'Art. 64',
        quote_snippet: 'It shall apply from 17 January 2025.',
        celex: '32022R2554',
        verified: true,
      },
      {
        framework: 'DORA',
        reference: 'Art. 6(1)',
        quote_snippet: DORA_ART6_QUOTE,
        celex: '32022R2554',
        verified: true,
      },
      {
        framework: 'DORA',
        reference: 'Art. 19(1)',
        quote_snippet: DORA_ART19_QUOTE,
        celex: '32022R2554',
        verified: true,
      },
      {
        framework: 'DORA',
        reference: 'Art. 26(1)',
        quote_snippet: 'shall carry out at least every 3 years advanced testing by means of TLPT',
        celex: '32022R2554',
        verified: true,
      },
      {
        framework: 'DORA',
        reference: 'Art. 28(1)',
        quote_snippet: DORA_ART28_QUOTE,
        celex: '32022R2554',
        verified: true,
      },
    ],
    confidence_score: 0.92,
    requires_expert_review: false,
    related_frameworks: ['NIS2'],
    caveats: [
      'The time limits for incident notification are set by the regulatory technical standards that supplement Article 19, not by the regulation.',
    ],
  },
  dora_art30: {
    answer:
      'Article 30 of DORA sets the minimum content of contracts with ICT third-party service providers. Every arrangement includes at least [1]: a complete description of the functions and services, the locations where data are processed and stored with prior notice of any change, the guarantees on availability, integrity and confidentiality, assistance in the event of an incident, the rights of access, inspection and audit, the termination rights and the exit strategies.\n\nWhen the services support critical or important functions further elements are added [2]: service levels with quantitative and qualitative targets, notification obligations, participation in resilience testing, conditions for subcontracting. All of this is part of ICT third-party risk management, an integral component of the risk management framework [3].',
    citations: [
      {
        framework: 'DORA',
        reference: 'Art. 30(2)',
        quote_snippet: 'The contractual arrangements on the use of ICT services shall include at least the following elements',
        celex: '32022R2554',
        verified: true,
      },
      {
        framework: 'DORA',
        reference: 'Art. 30(3)',
        quote_snippet:
          'The contractual arrangements on the use of ICT services supporting critical or important functions shall include, in addition to the elements referred to in paragraph 2, at least the following',
        celex: '32022R2554',
        verified: true,
      },
      {
        framework: 'DORA',
        reference: 'Art. 28(1)',
        quote_snippet: DORA_ART28_QUOTE,
        celex: '32022R2554',
        verified: true,
      },
    ],
    confidence_score: 0.93,
    requires_expert_review: false,
    related_frameworks: ['NIS2'],
    caveats: ['The regulatory technical standards on the policy for ICT providers specify the contractual content.'],
  },
  nis2: {
    answer:
      "Directive (EU) 2022/2555 (NIS2) applies to entities in the sectors listed in Annexes I and II that are at least medium-sized enterprises [1]. For significant incidents it provides for a notification in three steps: an early warning within 24 hours of becoming aware of the incident [2], a notification with the initial assessment within 72 hours [3] and a final report within one month of the notification [4]. An incident is significant when it has caused or can cause severe operational disruption of the services or financial loss for the entity [5], or when it has affected or can affect other persons by causing considerable damage.\n\nIn Italy the directive is transposed by Legislative Decree 138/2024: notifications go to CSIRT Italia, and in-scope entities register, or update their registration, on the platform of the National Cybersecurity Agency (ACN) from 1 January to 28 February of each year [6].",
    citations: [
      {
        framework: 'NIS2',
        reference: 'Art. 2(1)',
        quote_snippet:
          'This Directive applies to public or private entities of a type referred to in Annex I or II which qualify as medium-sized enterprises',
        celex: '32022L2555',
        verified: true,
      },
      {
        framework: 'NIS2',
        reference: 'Art. 23(4), point (a)',
        quote_snippet: NIS2_ART23_4A_QUOTE,
        celex: '32022L2555',
        verified: true,
      },
      {
        framework: 'NIS2',
        reference: 'Art. 23(4), point (b)',
        quote_snippet:
          'without undue delay and in any event within 72 hours of becoming aware of the significant incident, an incident notification',
        celex: '32022L2555',
        verified: true,
      },
      {
        framework: 'NIS2',
        reference: 'Art. 23(4), point (d)',
        quote_snippet: 'a final report not later than one month after the submission of the incident notification under point (b)',
        celex: '32022L2555',
        verified: true,
      },
      {
        framework: 'NIS2',
        reference: 'Art. 23(3)',
        quote_snippet:
          'it has caused or is capable of causing severe operational disruption of the services or financial loss for the entity concerned',
        celex: '32022L2555',
        verified: true,
      },
      {
        framework: 'IT',
        title: 'Legislative Decree No 138 of 4 September 2024',
        reference: 'Art. 7(1) and Art. 25',
        quote_snippet: '',
        url: 'https://www.normattiva.it/uri-res/N2Ls?urn:nir:stato:decreto.legislativo:2024-09-04;138',
        verified: false,
      },
    ],
    confidence_score: 0.9,
    requires_expert_review: false,
    related_frameworks: ['DORA', 'GDPR'],
    caveats: [ITALIAN_LAW_CAVEAT],
  },
  taxonomy: {
    answer:
      'Regulation (EU) 2020/852 (the Taxonomy) sets out when an economic activity is environmentally sustainable: it must contribute substantially to at least one of the six environmental objectives, not significantly harm the others, comply with the minimum safeguards and with the technical screening criteria [1]. The six objectives are climate change mitigation and adaptation, the sustainable use of water and marine resources, the circular economy, pollution prevention and biodiversity [2].\n\nThe minimum safeguards are procedures that ensure alignment with the OECD Guidelines for Multinational Enterprises and the UN Guiding Principles on Business and Human Rights [3]. The obligation to publish the share of turnover, capital expenditure and operating expenditure associated with environmentally sustainable activities concerns the undertakings subject to sustainability reporting [4]: after Omnibus I, those with more than 1,000 employees and a net turnover above EUR 450 million.',
    citations: [
      {
        framework: 'TAXONOMY',
        reference: 'Art. 3',
        quote_snippet:
          'an economic activity shall qualify as environmentally sustainable where that economic activity: (a) contributes substantially to one or more of the environmental objectives set out in Article 9',
        celex: '32020R0852',
        verified: true,
      },
      {
        framework: 'TAXONOMY',
        reference: 'Art. 9',
        quote_snippet:
          '(a) climate change mitigation; (b) climate change adaptation; (c) the sustainable use and protection of water and marine resources; (d) the transition to a circular economy; (e) pollution prevention and control; (f) the protection and restoration of biodiversity and ecosystems',
        celex: '32020R0852',
        verified: true,
      },
      {
        framework: 'TAXONOMY',
        reference: 'Art. 18(1)',
        quote_snippet:
          'shall be procedures implemented by an undertaking that is carrying out an economic activity to ensure the alignment with the OECD Guidelines for Multinational Enterprises and the UN Guiding Principles on Business and Human Rights',
        celex: '32020R0852',
        verified: true,
      },
      {
        framework: 'TAXONOMY',
        reference: 'Art. 8(1)',
        quote_snippet:
          "shall include in its non-financial statement or consolidated non-financial statement information on how and to what extent the undertaking's activities are associated with economic activities that qualify as environmentally sustainable",
        celex: '32020R0852',
        verified: true,
      },
    ],
    confidence_score: 0.88,
    requires_expert_review: false,
    related_frameworks: ['CSRD'],
    caveats: ['The technical screening criteria are in the delegated acts of the Commission and are updated over time.'],
  },
  cross_ai_gdpr: {
    answer:
      'Under the AI Act: AI systems used to evaluate the creditworthiness of natural persons or establish their credit score are high-risk, except those used to detect financial fraud [1]. For these systems a risk management system is established [2] and whoever uses them (the deployer) performs, before use, an assessment of the impact on fundamental rights [3]. The high-risk requirements for the systems of Annex III apply from 2 December 2027 [4].\n\nUnder the GDPR: a credit decision taken solely by automated means falls under Article 22: the data subject has the right not to be subject to it when it produces legal effects or similarly significantly affects him or her [5], and a systematic and extensive evaluation of personal aspects based on automated processing requires a data protection impact assessment [6].\n\nThe two regimes add up: both the GDPR impact assessment and the fundamental rights assessment of the AI Act are needed, and the second may refer to the first for the parts already covered (Article 27(4)).',
    citations: [
      {
        framework: 'AI_ACT',
        reference: 'Annex III, point 5(b)',
        quote_snippet:
          'AI systems intended to be used to evaluate the creditworthiness of natural persons or establish their credit score, with the exception of AI systems used for the purpose of detecting financial fraud',
        celex: '32024R1689',
        verified: true,
      },
      {
        framework: 'AI_ACT',
        reference: 'Art. 9(1)',
        quote_snippet: AI_ACT_ART9_QUOTE,
        celex: '32024R1689',
        verified: true,
      },
      {
        framework: 'AI_ACT',
        reference: 'Art. 27(1)',
        quote_snippet: 'shall perform an assessment of the impact on fundamental rights that the use of such system may produce',
        celex: '32024R1689',
        verified: true,
      },
      {
        framework: 'AI_ACT',
        reference: 'Art. 113, third paragraph, point (c)(i)',
        quote_snippet: AI_ACT_ART113_ANNEX3_QUOTE,
        celex: '32024R1689',
        verified: true,
      },
      {
        framework: 'GDPR',
        reference: 'Art. 22(1)',
        quote_snippet:
          'The data subject shall have the right not to be subject to a decision based solely on automated processing, including profiling, which produces legal effects concerning him or her or similarly significantly affects him or her.',
        celex: '32016R0679',
        verified: true,
      },
      {
        framework: 'GDPR',
        reference: 'Art. 35(3), point (a)',
        quote_snippet:
          'a systematic and extensive evaluation of personal aspects relating to natural persons which is based on automated processing, including profiling, and on which decisions are based that produce legal effects concerning the natural person or similarly significantly affect the natural person',
        celex: '32016R0679',
        verified: true,
      },
    ],
    confidence_score: 0.89,
    requires_expert_review: false,
    related_frameworks: ['DORA'],
    caveats: ['How the two assessments are coordinated has to be decided on the actual case, with the data protection officer.'],
  },
  cross_dora_nis2: {
    answer:
      'Under DORA: Regulation (EU) 2022/2554 is the sector-specific act for the digital operational resilience of financial entities: ICT risk management framework [1], reporting of major incidents [2], resilience testing and management of third-party providers.\n\nUnder NIS2: Directive (EU) 2022/2555 covers essential and important entities with risk-management measures and the notification of significant incidents in three steps (24 hours, 72 hours, one month) [3].\n\nHow they relate: where a sector-specific Union act requires risk-management measures or incident notification that are at least equivalent in effect, the corresponding provisions of NIS2 do not apply to those entities [4]; DORA is considered such a sector-specific act for financial entities [5]. A bank therefore applies DORA for risk management and incident notification.',
    citations: [
      {
        framework: 'DORA',
        reference: 'Art. 6(1)',
        quote_snippet: DORA_ART6_QUOTE,
        celex: '32022R2554',
        verified: true,
      },
      {
        framework: 'DORA',
        reference: 'Art. 19(1)',
        quote_snippet: DORA_ART19_QUOTE,
        celex: '32022R2554',
        verified: true,
      },
      {
        framework: 'NIS2',
        reference: 'Art. 23(4), point (a)',
        quote_snippet: NIS2_ART23_4A_QUOTE,
        celex: '32022L2555',
        verified: true,
      },
      {
        framework: 'NIS2',
        reference: 'Art. 4(1)',
        quote_snippet:
          'the relevant provisions of this Directive, including the provisions on supervision and enforcement laid down in Chapter VII, shall not apply to such entities',
        celex: '32022L2555',
        verified: true,
      },
      {
        framework: 'DORA',
        reference: 'Art. 1(2)',
        quote_snippet:
          'this Regulation shall be considered a sector-specific Union legal act for the purposes of Article 4 of that Directive',
        celex: '32022R2554',
        verified: true,
      },
    ],
    confidence_score: 0.92,
    requires_expert_review: false,
    related_frameworks: ['GDPR'],
    caveats: [],
  },
}

export const SUGGESTED_QUESTIONS_EN = [
  'Does our company with 600 employees still fall under the CSRD after the Omnibus?',
  'Does a chatbot on the company website have to say that it is an AI?',
  'Which incidents must be notified within 24 hours under NIS2?',
  'Do we have to train the employees who use AI?',
]

export const NOT_COVERED_EN =
  'This question is not among the examples of the demo. Outside the demo NormaAI searches the official texts of the corpus and answers with the passages of law, or abstains when the text is not enough.'
