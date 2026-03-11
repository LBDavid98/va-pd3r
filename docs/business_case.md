# PD3r: Business Case for Internal AI Capability

> VHA Digital Health Office — March 2026

---

## The Problem

Writing federal position descriptions (PDs) is slow, inconsistent, and expensive.

- A single PD takes **8–40 hours** of combined management and HR specialist time depending on complexity and number of resubmissions
- Drafts frequently fail to score at target level during classification review, requiring rework cycles and arguments.
- FES factor evaluation requires deep knowledge of 9 factors across 350+ level definitions
- HR specialists juggle 100+ GS series, each with distinct duty templates
- Hiring timelines stretch months while PDs sit in drafting queues. This leads to overburden of VA staff and increased overtime costs at a facility level. 

---

## What PD3r Does

PD3r (Pete) is a conversational AI agent that **writes complete, OPM-compliant position descriptions** through a guided interview process.

### Workflow

| Phase | What Happens |
|-------|-------------|
| **Interview** | Pete asks  structured questions, collecting position details conversationally |
| **FES Evaluation** | Automatically evaluates 9 FES factors and calculates grade recommendation. Evaluates supervisory factors as well as a part of the interview. |
| **Drafting** | Generates 8 PD elements using series-specific templates and collected data |
| **QA Review** | Each element checked against requirements; auto-rewrites on failure |
| **Export** | Produces formatted Word (.docx) or Markdown documents |

### Key Capabilities

- **Real-time chat interface** with streaming responses via WebSocket
- **OPM compliance built in** — FES factors, DOES statements, series templates for 100+ GS series
- **Automated quality assurance** — every draft element validated against requirements
- **Field overrides** — Users can correct any collected data inline
- **RAG knowledge base** — answers HR policy questions during the interview using vector stored HR policy documents. Answers come with page and document level citation.
- **Export to Word/Markdown** — production-ready documents

---

## What This Would Cost to Contract Out

### Industry Benchmarks

Federal software development contracts for AI/ML applications typically run:

| Firm Type | Estimated Cost | Timeline | Team Size |
|-----------|---------------|----------|-----------|
| Small business (8(a), SDVOSB) | $800K–$1.2M | 9–12 months | 4–6 |
| Mid-tier (Booz Allen, ICF, Accenture Federal) | $1.5M–$2.5M | 12–18 months | 6–10 |
| Large integrator (Deloitte, SAIC, Leidos) | $2.5M–$4M+ | 18–24 months | 8–15 |

### Cost Breakdown (Mid-Tier Estimate)

| Phase | Staff-Months | Cost |
|-------|-------------|------|
| Discovery & Requirements | 2–3 | $80K–$150K |
| UX/UI Design (Section 508) | 2–3 | $80K–$150K |
| Backend + AI Pipeline | 6–9 | $250K–$450K |
| Frontend Development | 3–4 | $120K–$200K |
| Domain Knowledge / SME | 2–3 | $80K–$150K |
| Prompt Engineering & LLM | 2–3 | $80K–$150K |
| RAG Pipeline & Knowledge Base | 1–2 | $50K–$100K |
| Testing & QA | 3–4 | $120K–$200K |
| DevOps / ATO Prep / Security | 2–4 | $80K–$200K |
| Documentation & Training | 1–2 | $50K–$100K |
| PM Overhead | 4–6 | $150K–$300K |
| **Total** | **28–43** | **$1.1M–$2.1M** |

### Why Contractors Charge This Much

- **AI/ML premium**: LLM integration is billed at $250–$350/hr "AI specialist" rates
- **Federal compliance**: ATO,  FedRAMP add a large overhaed to any project contracted
- **Domain complexity**: OPM rules, FES factors, series templates require paid SME time
- **Overhead**: Clearances, COR reporting, subcontractor markup, travel, facilities

---

## What PD3r Was Actually Built With

| Resource | Detail |
|----------|--------|
| **Team** | 1 developer |
| **Timeline** | 4 months |
| **External cost** | OpenAI API usage only (~$0.50–$1.00 per PD generated) before fine tuning |
| **Infrastructure** | Can be served in Docker containers on existing VA infrastructure |

---

## The Argument for Internal Capability

### Cost Avoidance

Building internally at a fraction of contract cost represents **$1M–$3M in cost avoidance** compared to procurement. That's before you consider procurement timelines. 

### Speed to Delivery

| Metric | Contract | Internal |
|--------|----------|----------|
| Time to first working prototype | 4–6 months | 2 months |
| Time to production-ready | 12–18 months | 4-6 months |
| Iteration cycle | Weeks (change orders) | Days |
| Feature request turnaround | Contract modification | Next sprint |

### Operational Advantages

- **No vendor lock-in** — we own the code, the prompts, the domain knowledge
- **Institutional knowledge stays internal** — OPM rules, FES logic, series templates are captured in code, not a contractor's proprietary system
- **Rapid iteration** — prompt engineering and feature changes deploy in hours, not months
- **Reusable patterns** — the LangGraph agent architecture applies to other VA workflows

### Risk Reduction

- **No procurement timeline** — no RFP, no evaluation, no protest risk
- **No contract modifications** — scope changes are commits, not change orders
- **Transparent AI** — we control the prompts, can audit every decision, trace every output
- **Data stays internal** — only anonymized position data reaches the LLM API
- **Agentic Coding** - Reduces the burden for both feature development and codebase maintenance with a proper SOP. 

---

## Technical Maturity

PD3r is not a prototype — it is a production-grade application.

| Metric | Value |
|--------|-------|
| Automated tests | 866+ |
| Test code | 12,500+ lines |
| Backend modules | 74 Python files |
| Frontend components | 32 React/TypeScript files |
| API endpoints | 15 REST + WebSocket |
| Graph nodes | 19 (LangGraph) |
| Architecture decisions documented | 10+ ADRs |
| Interview fields | 30+ with conditional logic |
| GS series supported | 100+ |
| Export formats | Word (.docx), Markdown (.md) |

---

## Operating Costs at Scale

### Assumptions

| Parameter | Value | Basis |
|-----------|-------|-------|
| Organization size | 350,000 employees | VHA workforce |
| Annual turnover rate | 7% | Pre-2025 federal average (retirements, resignations, transfers) |
| Positions requiring PD work | 2/3 of turnover | Mix of rewrites and revisions |
| **Annual PD volume** | **~16,300 PDs/year** | 350K × 7% × 2/3 |

### API Cost per PD

PD3r uses a blended model strategy — gpt-4o-mini for lightweight tasks (intent classification, approval detection) and gpt-4o for substantive work (drafting, QA review, FES evaluation).

| Call Type | Model | Calls/PD | Est. Tokens | Cost/PD |
|-----------|-------|----------|-------------|---------|
| Intent classification | gpt-4o-mini | ~15 | 18K | $0.005 |
| Agent reasoning (interview) | gpt-4o | ~15 | 52K | $0.17 |
| FES evaluation | gpt-4o | 9 | 27K | $0.09 |
| Draft generation | gpt-4o | 12 | 60K | $0.19 |
| QA review | gpt-4o | 12 | 42K | $0.13 |
| Auto-rewrites (~25% of elements) | gpt-4o | ~3 | 17K | $0.05 |
| Approval detection | gpt-4o-mini | ~12 | 7K | $0.002 |
| **Total per PD** | | **~78 calls** | **~223K tokens** | **~$0.64** |

> Token estimates based on measured context sizes in production sessions. Actual costs vary with position complexity and interview length.

### Annual Operating Budget

| Cost Category | Annual Cost | Notes |
|---------------|-------------|-------|
| **Development & support** (1 FTEE GS-14) | $193,000 | Loaded cost (base + locality + benefits) |
| **Ongoing maintenance** (0.25 FTEE GS-14) | $48,300 | Prompt tuning, updates, monitoring |
| **LLM API costs** (16,300 PDs × $0.64) | $10,400 | Blended gpt-4o + gpt-4o-mini |
| **Infrastructure** (app servers + DB) | $8,400 | Docker on existing VA cloud |
| **Year 1 total** (build + operate) | **$260,100** | Includes full development FTEE |
| **Year 2+ total** (operate only) | **$67,100** | 0.25 FTEE maintenance + API + infra |

> **Steady-state cost per PD (fully loaded): ~$4.10** including maintenance staff, infrastructure, and API.
> Compare to ~$540 per PD in combined management + HR labor for traditional drafting.

### Model Cost Sensitivity

If OpenAI pricing drops (as it has ~50% per year historically) or the organization switches to a cheaper provider:

| Model Scenario | API Cost/PD | Annual API Cost (16,300 PDs) |
|---------------|-------------|------------------------------|
| Current (gpt-4o + mini blend) | $0.64 | $10,400 |
| GPT-4o-mini only (quality tradeoff) | $0.04 | $650 |
| 50% price reduction (expected in 12 mo) | $0.32 | $5,200 |
| Self-hosted open model (Llama, etc.) | ~$0.10 | $1,630 |

---

## Potential Impact

### Loaded Hourly Rates (2026)

Labor costs use OPM 2026 base pay (Step 5) plus average locality (~25%) and benefits loading factor (~36%, per OMB Circular A-76):

| Role | Base + Locality | Loaded Annual | Loaded Hourly |
|------|----------------|---------------|---------------|
| Management (GS-12) | ~$107,600 | ~$146,300 | ~$70 |
| HR Specialist (GS-11) | ~$89,800 | ~$122,100 | ~$59 |
| Developer/Support (GS-14) | ~$142,200 | ~$193,400 | ~$93 |

### Per-PD Time and Cost — Traditional vs. PD3r

PD authoring is a collaboration between **management** (who drafts the position description) and **HR** (who reviews for OPM compliance, classifies, and iterates). PD3r eliminates most of the drafting labor and reduces revision cycles by providing OPM-compliant first drafts with built-in QA.

#### Traditional Process

| Task | Who | Hours | Loaded Cost |
|------|-----|-------|-------------|
| First draft (writing) | Management (GS-12) | 4.0 hrs | $280 |
| Back-and-forth (revisions) | Management (GS-12) | 2.0 hrs | $140 |
| Back-and-forth (compliance review) | HR Specialist (GS-11) | 2.0 hrs | $118 |
| **Total per PD** | | **8.0 hrs** | **$538** |

#### With PD3r

| Task | Who | Hours | Loaded Cost | Reduction |
|------|-----|-------|-------------|-----------|
| First draft (guided interview) | Management (GS-12) | 0.2 hrs (~12 min) | $14 | 95% |
| Back-and-forth (revisions) | Management (GS-12) | 1.0 hr | $70 | 50% |
| Back-and-forth (compliance review) | HR Specialist (GS-11) | 1.0 hr | $59 | 50% |
| **Total per PD** | | **2.2 hrs** | **$143** | **73%** |

> The 95% writing reduction reflects PD3r generating complete, structured drafts from interview data — management time drops from 4 hours of writing to ~12 minutes of answering guided questions. The 50% revision reduction reflects fewer compliance issues in first drafts (FES alignment, DOES format, word count targets) — though hiring manager preferences and organizational nuance still require human review.

### Per-PD Savings

| | Traditional | With PD3r | Savings |
|---|-----------|-----------|---------|
| Management hours (GS-12) | 6.0 hrs | 1.2 hrs | 4.8 hrs |
| HR hours (GS-11) | 2.0 hrs | 1.0 hr | 1.0 hr |
| **Total hours** | **8.0 hrs** | **2.2 hrs** | **5.8 hrs** |
| **Total labor cost** | **$538** | **$143** | **$395** |

### At Scale (350,000-Employee Organization)

| Metric | Value |
|--------|-------|
| Annual PDs requiring work | 16,300 |
| | |
| **Management time recovered** | |
| Hours saved per PD (GS-12) | 4.8 |
| Total management hours recovered | 78,240 |
| Management labor value recovered | $5.48M |
| | |
| **HR time recovered** | |
| Hours saved per PD (GS-11) | 1.0 |
| Total HR hours recovered | 16,300 |
| HR labor value recovered | $0.96M |
| | |
| **Combined savings** | |
| **Total hours recovered annually** | **94,540** |
| **Total labor reallocation value** | **$6.44M** |
| Annual operating cost (Year 2+ steady state) | $67K |
| **Net annual savings** | **$6.37M** |
| **Return on operating cost** | **96:1** |

### What 94,500 Recovered Hours Means

- **78,240 management hours** — equivalent to ~38 FTE managers freed from PD writing. These are hiring managers, supervisors, and program leads who can return focus to mission-critical work
- **16,300 HR specialist hours** — equivalent to ~8 FTE HR specialists freed from PD revision cycles, available for classification reviews, workforce planning, and hiring actions
- **Hiring timeline compression** — PDs that sat in drafting queues for weeks can be completed same-day
- **Consistency improvement** — every PD follows the same OPM-compliant structure, reducing rework at classification

---

## Risks and Mitigations

| Risk | Mitigation |
|------|-----------|
| LLM hallucination | QA review node validates every element; human review before finalization |
| API dependency (OpenAI) | Architecture supports model swapping (Anthropic, Azure OpenAI, local models) |
| ATO requirements | Containerized, auditable |
| Adoption resistance | Conversational UX designed for non-technical HR users |
| Single developer | Comprehensive test suite + documentation enable knowledge transfer |

---

## Recommendation

Invest in scaling PD3r internally rather than contracting out. Consider additional agentic workflows for common administrative tasks like drafting contracting documents, common report formatting, less common but critical reports where an interview can improve quality of information received (Joint Patient Safety Reporting for example). 

1. **Continue development** — add remaining features (approval workflows, org templates)
2. **Pilot with 2–3 HR teams** — validate time savings with real users
3. **Pursue ATO** — containerized architecture simplifies the path
4. **Document ROI** — track PDs generated, time saved, compliance rates
5. **Extend the pattern** — apply the agent architecture to other VA document workflows

---

## Summary

| | Contract | Internal (PD3r) |
|---|----------|----------------|
| **Build cost** | $1.5M–$4M | <$50K (API costs + developer time) |
| **Annual operating cost (steady state)** | $200K–$500K (O&M contract) | ~$67K (0.25 FTEE GS-14 + API + infra) |
| **Cost per PD** | ~$538 (management + HR labor) | ~$4.10 (fully loaded) |
| **Annual labor savings (350K org)** | — | $6.44M (94,540 hours recovered) |
| **Net annual savings** | — | $6.37M (after operating costs) |
| **ROI on operating cost** | — | 96:1 |
| **Timeline** | 12–24 months | Already built |
| **Ownership** | Vendor-dependent | VA-owned |
| **Iteration speed** | Change orders | Next Sprint |
| **Domain knowledge** | Leaves with contractor | Captured in code |

**PD3r demonstrates that internal AI capability can deliver enterprise-grade tools at a fraction of the cost and timeline of traditional federal IT procurement. At scale, it recovers 94,500 hours annually — the equivalent of 38 managers and 8 HR specialists — freeing them from PD drafting work while netting $6.4M in annual savings against a $67K steady-state operating cost.**
