# Knowledge Base - Federal Position Description Resources

This folder contains official .gov documents for federal position classification and position description writing. All sources are from OPM (Office of Personnel Management) and VA (Department of Veterans Affairs).

## Document Inventory

### OPM Core Handbooks (ESSENTIAL - Download First)

These are the foundational documents for GS position classification:

| Document | Description | Download URL |
|----------|-------------|--------------|
| **Introduction to Position Classification Standards** | Detailed description of the GS Classification System for white collar occupations | https://www.opm.gov/policy-data-oversight/classification-qualifications/classifying-general-schedule-positions/introduction-to-position-classification-standards.pdf |
| **The Classifier's Handbook** | Guidance on how to classify white collar positions within the General Schedule | https://www.opm.gov/policy-data-oversight/classification-qualifications/classifying-general-schedule-positions/classifierhandbook.pdf |
| **Handbook of Occupational Groups & Families** | Definitions of white collar occupations (Part I) | https://www.opm.gov/policy-data-oversight/classification-qualifications/classifying-general-schedule-positions/occupationalhandbook.pdf |

### OPM Functional Guides (Grade Evaluation)

Functional guides determine the grade of broad categories of Federal white collar work:

| Guide | Download URL |
|-------|--------------|
| Administrative Analysis Grade Evaluation Guide | https://www.opm.gov/policy-data-oversight/classification-qualifications/classifying-general-schedule-positions/functional-guides/gsadmnanal.pdf |
| Grade Level Guide for Clerical and Assistance Work | https://www.opm.gov/policy-data-oversight/classification-qualifications/classifying-general-schedule-positions/functional-guides/gscler.pdf |
| General Schedule Leader Grade Evaluation Guide | https://www.opm.gov/policy-data-oversight/classification-qualifications/classifying-general-schedule-positions/functional-guides/gsleader.pdf |
| General Schedule Supervisory Guide | https://www.opm.gov/policy-data-oversight/classification-qualifications/classifying-general-schedule-positions/functional-guides/gssg.pdf |
| Policy Analysis Grade-Evaluation Guide | https://www.opm.gov/policy-data-oversight/classification-qualifications/classifying-general-schedule-positions/functional-guides/gspolcy.pdf |
| Guide for the Evaluation of Program Specialist Positions | https://www.opm.gov/policy-data-oversight/classification-qualifications/classifying-general-schedule-positions/functional-guides/gsprogspec.pdf |
| Research Grade Evaluation Guide | https://www.opm.gov/policy-data-oversight/classification-qualifications/classifying-general-schedule-positions/functional-guides/gsresrch.pdf |
| Writing and Editing Grade Evaluation Guide | https://www.opm.gov/policy-data-oversight/classification-qualifications/classifying-general-schedule-positions/functional-guides/gswrite.pdf |

### OPM Position Classification Standards by Series

#### Information Technology (2200 Group)
| Series | Standard | Download URL |
|--------|----------|--------------|
| 2210 | IT Management (Job Family Standard) | https://www.opm.gov/policy-data-oversight/classification-qualifications/classifying-general-schedule-positions/standards/2200/gs2210.pdf |

#### Administrative & Program (0300 Group)
| Series | Standard | Download URL |
|--------|----------|--------------|
| 0301 | Miscellaneous Administration and Program | https://www.opm.gov/policy-data-oversight/classification-qualifications/classifying-general-schedule-positions/standards/0300/gs0301.pdf |
| 0340 | Program Management | https://www.opm.gov/policy-data-oversight/classification-qualifications/classifying-general-schedule-positions/standards/0300/gs0340.pdf |
| 0341 | Administrative Officer | https://www.opm.gov/policy-data-oversight/classification-qualifications/classifying-general-schedule-positions/standards/0300/gs0341.pdf |
| 0343 | Management and Program Analysis | https://www.opm.gov/policy-data-oversight/classification-qualifications/classifying-general-schedule-positions/standards/0300/gs0343.pdf |

#### Human Resources (0200 Group)
| Series | Standard | Download URL |
|--------|----------|--------------|
| 0200 | HR Management (Job Family Standard - Administrative) | https://www.opm.gov/policy-data-oversight/classification-qualifications/classifying-general-schedule-positions/standards/0200/gs0200a.pdf |
| 0200 | HR Assistance (Job Family Standard - Assistance) | https://www.opm.gov/policy-data-oversight/classification-qualifications/classifying-general-schedule-positions/standards/0200/gs0200b.pdf |

#### Accounting & Budget (0500 Group)
| Series | Standard | Download URL |
|--------|----------|--------------|
| 0500 | Accounting, Auditing, and Budget (Job Family Standard) | https://www.opm.gov/policy-data-oversight/classification-qualifications/classifying-general-schedule-positions/standards/0500/gs0500a.pdf |
| 0505 | Financial Management | https://www.opm.gov/policy-data-oversight/classification-qualifications/classifying-general-schedule-positions/standards/0500/gs0505.pdf |

#### Contracting (1100 Group)
| Series | Standard | Download URL |
|--------|----------|--------------|
| 1102 | Contracting | https://www.opm.gov/policy-data-oversight/classification-qualifications/classifying-general-schedule-positions/standards/1100/gs1102.pdf |
| 1109 | Grants Management | https://www.opm.gov/policy-data-oversight/classification-qualifications/classifying-general-schedule-positions/standards/1100/gs1109.pdf |

#### Engineering (0800 Group)
| Series | Standard | Download URL |
|--------|----------|--------------|
| 0800 | Engineering (Job Family Standard - Professional) | https://www.opm.gov/policy-data-oversight/classification-qualifications/classifying-general-schedule-positions/standards/0800/gs0800p.pdf |
| 0800 | Engineering Technical (Job Family Standard) | https://www.opm.gov/policy-data-oversight/classification-qualifications/classifying-general-schedule-positions/standards/0800/gs0800t.pdf |

---

## VA Publications (Position Classification)

Key VA handbooks for HR and position classification:

| Document Number | Title | Download URL |
|-----------------|-------|--------------|
| VA Handbook 5003 | Position Classification and Position Management Part I | https://www.va.gov/vapubs/viewPublication.asp?Pub_ID=567 |
| VA Handbook 5003 Master | Position Classification, Job Grading, and Position Management (through Change 5) | https://www.va.gov/vapubs/viewPublication.asp?Pub_ID=566 |
| VA Handbook 5003/6 | Position Classification and Position Management | https://www.va.gov/vapubs/viewPublication.asp?Pub_ID=1242 |
| VA Handbook 5002 | Strategic Workforce and Succession Planning | https://www.va.gov/vapubs/viewPublication.asp?Pub_ID=1218 |
| VA Handbook 5005 Master | Staffing (through Change 174) | https://www.va.gov/vapubs/viewPublication.asp?Pub_ID=1248 |
| VA Handbook 5007 Master | Pay Administration (through Change 61) | https://www.va.gov/vapubs/viewPublication.asp?Pub_ID=576 |

---

## Download Instructions

### Using curl (macOS/Linux)
```bash
# Create a downloads subfolder
mkdir -p knowledge/pdfs

# Download OPM core handbooks
curl -L -o knowledge/pdfs/introduction-to-position-classification.pdf \
  "https://www.opm.gov/policy-data-oversight/classification-qualifications/classifying-general-schedule-positions/introduction-to-position-classification-standards.pdf"

curl -L -o knowledge/pdfs/classifier-handbook.pdf \
  "https://www.opm.gov/policy-data-oversight/classification-qualifications/classifying-general-schedule-positions/classifierhandbook.pdf"

curl -L -o knowledge/pdfs/occupational-handbook.pdf \
  "https://www.opm.gov/policy-data-oversight/classification-qualifications/classifying-general-schedule-positions/occupationalhandbook.pdf"

# Download key functional guides
curl -L -o knowledge/pdfs/supervisory-guide.pdf \
  "https://www.opm.gov/policy-data-oversight/classification-qualifications/classifying-general-schedule-positions/functional-guides/gssg.pdf"

# Download IT series standard (2210)
curl -L -o knowledge/pdfs/gs2210-it-management.pdf \
  "https://www.opm.gov/policy-data-oversight/classification-qualifications/classifying-general-schedule-positions/standards/2200/gs2210.pdf"
```

---

## Source Links

- **OPM Classification Main Page**: https://www.opm.gov/policy-data-oversight/classification-qualifications/classifying-general-schedule-positions/
- **OPM Qualification Standards**: https://www.opm.gov/policy-data-oversight/classification-qualifications/general-schedule-qualification-standards/
- **OPM Functional Guides**: https://www.opm.gov/policy-data-oversight/classification-qualifications/classifying-general-schedule-positions/#url=Functional-Guides
- **VA Publications Portal**: https://www.va.gov/vapubs/
- **OPM Contact**: fedclass@opm.gov

---

## Priority Documents for PD3r

For the position description writing agent, these are highest priority:

1. **The Classifier's Handbook** - Core methodology for writing PDs
2. **Introduction to Position Classification Standards** - Factor Evaluation System (FES) details
3. **General Schedule Supervisory Guide** - Supervisory factor levels
4. **GS-2210 IT Management Standard** - If focusing on IT positions
5. **Management and Program Analysis (0343)** - Common administrative series

---

*Last updated: January 2026*

---

## RAG Knowledge Base Setup

PD3r uses a vector store to enable RAG (Retrieval-Augmented Generation) for answering HR-specific questions. The knowledge base is built from the PDF documents in `unprocessed_pdfs/`.

### Directory Structure

```
knowledge/
├── README.md           # This file
├── unprocessed_pdfs/   # Place PDF files here for ingestion
└── vector_store/       # Generated - DO NOT commit (in .gitignore)
```

### Building the Knowledge Base

#### Prerequisites

1. **Download PDFs**: Download the relevant OPM documents from the URLs above and place them in `knowledge/unprocessed_pdfs/`
2. **Set API Key**: Ensure `OPENAI_API_KEY` is set (for embeddings)

#### Run Ingestion

```bash
# Build the vector store (first time)
poetry run python scripts/ingest_knowledge.py

# Force rebuild (after adding new PDFs)
poetry run python scripts/ingest_knowledge.py --rebuild

# Custom settings
poetry run python scripts/ingest_knowledge.py \
    --pdf-dir /path/to/pdfs \
    --chunk-size 1000 \
    --chunk-overlap 100
```

#### Ingestion Process

1. **Load**: PyPDF loads all PDFs from `unprocessed_pdfs/`
2. **Chunk**: Documents are split into ~1000 character chunks with 100 char overlap
3. **Embed**: OpenAI's `text-embedding-3-small` creates vector embeddings
4. **Store**: ChromaDB persists embeddings to `vector_store/`

### Adding New Documents

1. Download new PDF to `knowledge/unprocessed_pdfs/`
2. Run `poetry run python scripts/ingest_knowledge.py --rebuild`
3. The entire knowledge base will be rebuilt

### Querying the Knowledge Base

The RAG system is automatically used when Pete detects an HR-specific question:

```python
# Manual query (for testing)
from src.tools.rag_tools import rag_lookup

results = rag_lookup("What is Factor 1 in the FES system?", k=4)
for doc, score in results:
    print(f"Score: {score:.3f} | Source: {doc.metadata['source_file']}")
    print(doc.page_content[:200])
```

### Troubleshooting

**"Vector store not found"**: Run the ingestion script first.

**Empty results**: Ensure PDFs are in `unprocessed_pdfs/` and re-run ingestion.

**Rate limits**: The ingestion process makes many embedding API calls. If you hit rate limits, wait and retry.

