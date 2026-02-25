export const FAKE_CALLS = [
  {
    id: 'call-001',
    title: 'Technical Validation — Evernorth Health',
    account: 'Evernorth Health',
    stage: 'Technical Validation',
    arr: '$1.2M',
    date: '2026-02-20',
    duration: '52 min',
    participants: ['Sarah Chen (AE)', 'Marcus Webb (SE)', 'Dr. Lisa Park (CTO)', 'James O\'Brien (Architect)'],
    summary: 'Deep technical session validating TiDB\'s HTAP capabilities against Evernorth\'s claims processing workload. CTO confirmed SingleStore is the primary competition. Team showed strong interest in TiFlash columnar performance — ran live benchmark queries on their anonymized dataset. Key concern: 24/7 ops team managing schema migrations during business hours.',
    competitor: 'SingleStore',
    risks: [
      'Legal review of BAA (Business Associate Agreement) is blocking — 3 week delay expected',
      'Ops team has zero Kubernetes experience — managed cloud required',
      'Budget cycle closes March 31 — must close by then or slip to Q3',
    ],
    nextSteps: [
      'SE to send TiFlash vs ClickHouse benchmark report by Feb 24',
      'AE to loop in PingCAP legal re: BAA template — this week',
      'Schedule POC kickoff for March 3, using their anonymized claims dataset',
      'Send managed cloud pricing for TiDB Cloud Dedicated — Thursday',
    ],
    questions: [
      'How does TiDB handle online schema changes at 50K TPS without downtime?',
      'What are the SLA guarantees for TiDB Cloud in us-east-1?',
      'Can TiFlash handle ad-hoc aggregations on 3 years of claims data?',
      'What does the migration path from SingleStore look like?',
    ],
    collateral: [
      { title: 'TiFlash vs ClickHouse Benchmark (Healthcare)', url: '#' },
      { title: 'HIPAA Compliance Overview', url: '#' },
      { title: 'Online DDL at Scale — Technical Blog', url: '#' },
    ],
    transcript: `Sarah: Thank you for joining us today Dr. Park, James. Let's dive right in. Marcus is going to walk through the HTAP benchmark results we ran last week.

Marcus: Absolutely. So we took the 50-million-row anonymized claims sample you shared and loaded it into TiDB. What you're seeing on screen is a real-time OLTP workload — 45,000 transactions per second — while simultaneously running this aggregation query against TiFlash. Notice the OLTP latency doesn't budge. P99 stays under 8ms.

Dr. Park: That's... actually impressive. Our SingleStore team struggled to maintain that separation at 30K TPS. What's the magic?

Marcus: Two storage engines in one cluster. TiKV handles OLTP with Raft consensus — strong consistency. TiFlash is a columnar replica that replicates asynchronously. The optimizer routes automatically based on query type. No manual routing, no ETL pipeline.

James: How does schema migration work at that scale? We run 24/7 and can't afford locks.

Marcus: Online DDL — zero downtime. Adding a column on a 500GB table takes under 10 seconds with no table lock. We use a shadow table approach. Happy to share the technical deep-dive on that.

Dr. Park: The BAA situation is our main blocker right now. Our legal team needs to review any vendor handling PHI adjacent infrastructure.

Sarah: Completely understood. I'll get our legal team to send over our standard BAA template today. This is something we've done with four other healthcare customers in the last 12 months.

Dr. Park: If we get through legal review — which I'm optimistic about — I'd want to do a full POC on our claims processing pipeline. Real data, real scale.

Marcus: That's exactly what we'd propose. March 3rd POC kickoff, 30-day evaluation on TiDB Cloud Dedicated in us-east-1. We'll provide a dedicated SE resource throughout.

Sarah: James, for the Kubernetes concern you raised — TiDB Cloud is fully managed. Your ops team doesn't touch k8s. We handle upgrades, failover, backups, the works.

James: That changes the picture significantly. Our ops team is MySQL-trained. If it's managed and MySQL-compatible, adoption friction drops dramatically.

Dr. Park: What does this cost for our projected workload?

Sarah: I'll send detailed pricing Thursday — but for your scale, TiDB Cloud Dedicated in us-east-1, you're looking in the range of $80K-120K annually for the infrastructure, plus the licensing. Well within your $1.2M initial conversation.`,
  },
  {
    id: 'call-002',
    title: 'POC Design Review — Northwind Health',
    account: 'Northwind Health',
    stage: 'POC',
    arr: '$820K',
    date: '2026-02-18',
    duration: '38 min',
    participants: ['Alex Rivera (AE)', 'Priya Nair (SE)', 'Tom Goldstein (VP Engineering)', 'Rachel Kim (Data Lead)'],
    summary: 'POC design session for claims data platform modernization. Team is evaluating TiDB against MySQL + Redshift current stack. Rachel expressed concern about DBA-free operations — current team relies heavily on manual tuning. Strong HIPAA discussion — Northwind processes 2M claims/day. POC agreed: 60-day evaluation starting March 1.',
    competitor: 'MySQL + Amazon Redshift',
    risks: [
      'DBA team resistant to change — champion is VP Eng, not DBA lead',
      'HIPAA BAA still in legal review queue',
      'Data migration complexity from Redshift — 6TB of historical data',
      'AWS-centric org — TiDB Cloud on AWS required, GCP not acceptable',
    ],
    nextSteps: [
      'Send POC success criteria document by Feb 22',
      'Confirm AWS us-east-1 region availability for POC cluster',
      'Schedule DBA team intro call — include TiDB compatibility talking points',
      'Rachel to share Redshift schema for migration assessment',
    ],
    questions: [
      'How does TiDB\'s query optimizer compare to Redshift for analytics?',
      'Can TiDB replace both MySQL and Redshift with a single cluster?',
      'What tooling exists for migrating from Redshift?',
      'How does auto-scaling work on TiDB Cloud?',
    ],
    collateral: [
      { title: 'MySQL to TiDB Migration Playbook', url: '#' },
      { title: 'TiDB vs MySQL + Redshift Architecture Comparison', url: '#' },
      { title: 'TiDB Cloud Auto-Scaling Overview', url: '#' },
    ],
    transcript: `Alex: Tom, Rachel — thanks for the time. Today we want to nail down the POC success criteria so both teams are aligned going in.

Tom: Sounds good. My main question: can TiDB actually replace both MySQL AND Redshift? Because if it can, that's a massive operational simplification for us.

Priya: That's exactly our pitch. Today you have MySQL handling OLTP — claims intake, member portal — and Redshift handling analytics and reporting. With TiDB HTAP, that's one cluster, one ops burden, one billing relationship.

Rachel: My concern is the analytics performance. We have some heavy aggregation queries — claims cohort analysis, readmission rates. Those are finely tuned in Redshift. TiFlash needs to match or beat that.

Priya: Fair. For the POC we'd propose loading your 90-day claims sample — what's that, roughly 180 million rows? — into TiFlash and running your five critical reports head-to-head. We'll document query times, resource utilization, and output validation.

Tom: That works. What about the MySQL side? Our DBA team has 15 years of MySQL tuning experience. They're skeptical.

Priya: TiDB is MySQL-protocol compatible. Same connection string, same client tools, same explain output format. Their skills transfer directly. We're not asking them to relearn — we're asking them to add one skill: horizontal scaling without sharding.

Rachel: The migration is what worries me most. 6TB of historical Redshift data.

Alex: We have a migration assessment service — let us analyze your Redshift schema. We'll come back with a risk-categorized migration plan within two weeks. No commitment needed for that assessment.

Tom: Let's nail down the POC terms. 60 days, starting March 1, AWS us-east-1, our anonymized dataset. What do you need from us?

Priya: Read access to a Redshift snapshot for migration assessment, your top 5 analytics queries for benchmarking, and a VPC peering setup from your AWS account to TiDB Cloud. We'll handle everything else.

Tom: Rachel, can we have that Redshift schema over by Friday?

Rachel: Yes, that's doable.

Alex: Perfect. I'll send the formal POC success criteria doc by Monday. Once we're both signed off on that, we're go for March 1.`,
  },
  {
    id: 'call-003',
    title: 'Business Case Presentation — Summit Retail',
    account: 'Summit Retail',
    stage: 'Business Case',
    arr: '$640K',
    date: '2026-02-15',
    duration: '44 min',
    participants: ['Jordan Mills (AE)', 'Kevin Zhang (SE)', 'Diana Flores (CFO)', 'Sam Park (CTO)'],
    summary: 'Business case presentation to CFO and CTO. Summit is evaluating TiDB to consolidate fragmented MySQL shards across 3 data centers. Current setup: 47 MySQL shards, 3 ops engineers dedicated to shard management. TCO analysis showed 40% infrastructure cost reduction. CFO pushed for ROI clarity on ops headcount reallocation. Deal is competitive with CockroachDB.',
    competitor: 'CockroachDB',
    risks: [
      'CFO wants 3-year TCO model — AE needs to produce by March 1',
      'CockroachDB has a foot in the door with the data team',
      'Internal champion (CTO) may not survive re-org rumored for Q2',
      'Multi-region requirement — need TiDB Cloud multi-region GA confirmation',
    ],
    nextSteps: [
      'AE to produce 3-year TCO model with headcount reallocation ROI — March 1',
      'SE to confirm multi-region availability for us-east-1 + us-west-2',
      'Schedule CockroachDB bake-off — week of March 10',
      'AE to identify secondary champion in case of re-org',
    ],
    questions: [
      'What is the migration path from 47 MySQL shards to TiDB?',
      'How does TiDB multi-region compare to CockroachDB multi-region?',
      'What is the typical ops headcount reduction after TiDB adoption?',
      'Can TiDB handle Black Friday traffic spikes without pre-sharding?',
    ],
    collateral: [
      { title: 'MySQL Sharding to TiDB Migration Guide', url: '#' },
      { title: 'TiDB vs CockroachDB Comparison', url: '#' },
      { title: 'Retail Customer Case Studies', url: '#' },
    ],
    transcript: `Jordan: Diana, Sam — thank you for making time. Today we want to present the business case for TiDB at Summit, specifically the TCO analysis and the operational impact story.

Diana: Before you start — I need to understand the ROI on headcount. I've got three engineers whose primary job is managing MySQL shards. If TiDB eliminates that, I need to see that in numbers.

Kevin: Let's start there. Currently you have 47 shards across 3 data centers. Each shard is a separate MySQL instance with its own replication lag monitoring, backup schedules, capacity planning. That's what your three engineers spend most of their time on.

Sam: They also handle cross-shard queries. Any query that touches multiple customers — like a national inventory report — requires manual aggregation at the application layer.

Kevin: With TiDB, you have one logical database. Horizontal scaling is automatic — TiDB adds nodes when utilization hits threshold. No manual resharding, no cross-shard query logic. Your engineers shift from shard wrangling to feature development.

Diana: What's the infrastructure cost comparison?

Kevin: We ran the numbers against your current AWS spend that Jordan shared. Today you're running 47 RDS MySQL instances, plus the EC2 for your application-layer aggregation. That's approximately $380K annually. TiDB Cloud Dedicated for your workload — validated against your peak QPS — is approximately $220K. That's a $160K direct infrastructure saving in year one.

Diana: And the headcount reallocation?

Jordan: Conservative estimate: two of those three engineers shift to new feature development. At average loaded cost for a senior engineer in your market, that's $280K in realized value. Combined: $440K year-one benefit against a $220K cost. 2x ROI in year one.

Sam: What's the Black Friday story? We 10x on traffic in November.

Kevin: TiDB Cloud auto-scaling. You define your min and max TiKV node count. During Black Friday you scale out within minutes — no pre-provisioning required. Scale back down after. You only pay for what you use.

Diana: The CockroachDB team made similar claims. What's different?

Kevin: CockroachDB uses a PostgreSQL wire protocol — your MySQL applications need code changes. TiDB is MySQL-compatible — same connection string, no code changes. For a migration from 47 MySQL shards, that matters enormously.

Sam: Fair point. Our entire engineering stack is MySQL-native.

Jordan: We'd like to propose a bake-off — week of March 10, same workload, both products. Let the data speak.

Diana: I can work with that. But I need that 3-year TCO model before March 1 if we're going to the board.

Jordan: You'll have it March 1. I'll send a preliminary draft Monday.`,
  },
];

export function getCall(id) {
  return FAKE_CALLS.find((c) => c.id === id) || null;
}

export const FAKE_PRIORITIES = [
  { account: 'Evernorth Health', stage: 'Technical Validation', value: '$1.2M', risk: 'BAA legal delay 3wk' },
  { account: 'Northwind Health', stage: 'POC', value: '$820K', risk: 'DBA champion resistance' },
  { account: 'Summit Retail', stage: 'Business Case', value: '$640K', risk: 'TCO model due Mar 1' },
];

export const FAKE_COACHING = [
  { account: 'Evernorth Health', happened: 'CTO engaged on TiFlash live benchmark — strong pull. BAA blocker identified.', next: 'Send BAA template today, schedule legal intro call by Friday.' },
  { account: 'Northwind Health', happened: 'DBA team resistant. VP Eng is champion but lacks DBA support.', next: 'Schedule dedicated DBA intro call — MySQL compat talking points.' },
  { account: 'Summit Retail', happened: 'CFO asked for 3yr TCO model. CockroachDB has a foot in the door.', next: 'Deliver TCO model by March 1 — include headcount reallocation ROI.' },
];
