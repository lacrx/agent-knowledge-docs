---
title: Bedrock Knowledge Bases
topics:
  - bedrock
  - knowledge-bases
  - aws
  - rag
  - search
skills:
  - integrate-bedrock-knowledge-bases
summary: >
  Architecture, trade-offs, and operational guidance for AWS Bedrock Knowledge Bases as managed RAG over private data.
aliases:
  - bedrock rag
  - aws knowledge base
  - bedrock vector search
related:
  - bedrock-llm-integration
last-updated: 2026-06-25
---

# Bedrock Knowledge Bases

## Overview

AWS Bedrock Knowledge Bases is a fully managed retrieval-augmented generation (RAG) service that lets you connect foundation models to your private data sources without building your own ingestion, chunking, embedding, or retrieval pipeline. You point it at an S3 bucket (or other supported source), configure chunking and embedding options, and Bedrock handles the rest: parsing documents, splitting them into chunks, generating vector embeddings, storing them in a managed or customer-owned vector store, and retrieving relevant chunks at query time to augment LLM responses.

The core value proposition is operational simplicity. Building a production RAG pipeline from scratch requires choosing and hosting an embedding model, standing up a vector database, writing chunking logic, building an ingestion pipeline with change detection, and wiring retrieval into your LLM call path. Bedrock Knowledge Bases collapses all of that into a managed service with a single API surface. The trade-off is reduced control over each stage of the pipeline.

This article covers architecture, data source patterns, retrieval behavior, alternatives, and operational considerations. It does not cover step-by-step provisioning.

> **Skill:** For Bedrock LLM integration patterns including model invocation and streaming, use the `integrate-bedrock-llm` skill.

---

## Core Architecture

A Bedrock Knowledge Base consists of five stages, each managed by the service:

| Stage | What Happens | Configurable? |
|-------|-------------|---------------|
| **Data Source** | Documents are read from S3 (or other connectors) | Yes -- bucket, prefix, file types |
| **Chunking** | Documents are split into passages | Yes -- strategy, chunk size, overlap |
| **Embedding** | Each chunk is converted to a vector | Yes -- embedding model selection |
| **Vector Store** | Embeddings are indexed for similarity search | Yes -- managed (OpenSearch Serverless) or customer-owned |
| **Retrieval + Generation** | Relevant chunks are fetched and fed to an LLM | Yes -- number of results, search type, model |

### Data Sources

The primary data source is S3. You specify a bucket and optional prefix, and Bedrock ingests supported file types (PDF, TXT, MD, HTML, CSV, DOCX, and others). Ingestion can be triggered manually via `StartIngestionJob` or scheduled.

Other connectors exist for Confluence, SharePoint, Salesforce, and web crawlers, but S3 remains the most common and predictable option. Each connector has its own sync behavior and limitations.

### Chunking Strategies

Bedrock offers several chunking approaches:

- **Fixed-size chunking** -- Split by token count with configurable overlap. Simple and predictable. Works well for homogeneous document types.
- **Default chunking** -- Bedrock's built-in heuristic splitting. Reasonable for mixed content but offers less control.
- **Hierarchical chunking** -- Produces parent and child chunks for multi-level retrieval. Useful when documents have clear section structure.
- **Semantic chunking** -- Splits based on embedding similarity between adjacent passages. Better for documents where topic boundaries do not align with fixed token counts.
- **No chunking** -- Each document is treated as a single chunk. Only viable for short documents.

Chunk size and overlap are the most impactful parameters. Chunks that are too small lose context; chunks that are too large dilute relevance and consume more of the LLM context window. A common starting point is 300-500 tokens with 10-20% overlap.

### Embedding Models

You choose an embedding model at knowledge base creation time. Options include Amazon Titan Embeddings and Cohere Embed models available through Bedrock. The embedding model determines the vector dimensionality and, more importantly, the semantic quality of retrieval. Once selected, changing the embedding model requires re-ingesting all documents.

### Vector Store Options

Bedrock can provision a managed OpenSearch Serverless collection automatically, or you can bring your own vector store:

| Option | Pros | Cons |
|--------|------|------|
| **Managed OpenSearch Serverless** | Zero setup, fully managed | Limited tuning, cost can be opaque |
| **Customer-owned OpenSearch Serverless** | More index configuration control | You manage the collection |
| **Amazon Aurora PostgreSQL (pgvector)** | Familiar SQL interface, existing Aurora investment | Scaling characteristics differ from purpose-built vector DBs |
| **Pinecone** | Purpose-built vector DB, good performance | Third-party dependency, additional cost |
| **Redis Enterprise Cloud** | Low-latency retrieval | Third-party dependency |

For most new projects, the managed OpenSearch Serverless option is the fastest path. Switch to a customer-owned store when you need specific index tuning, cost control, or multi-tenancy isolation.

---

## Retrieval and Response Generation

At query time, the `RetrieveAndGenerate` API performs two steps:

1. **Retrieve** -- The query is embedded using the same model used at ingestion time, then a similarity search runs against the vector store. You can configure the number of results returned (default 5) and the search type (semantic, hybrid with keyword matching, or reranking).
2. **Generate** -- Retrieved chunks are injected into the LLM prompt as context, and the model generates a response grounded in those chunks.

You can also call `Retrieve` alone to get raw chunks without LLM generation, which is useful when you want to control the prompt template or use a different model for generation.

### Search Types

- **Semantic search** -- Pure vector similarity. Works well when queries and documents use similar vocabulary.
- **Hybrid search** -- Combines vector similarity with keyword matching. Better for queries containing specific terms, identifiers, or proper nouns that pure semantic search might miss.
- **Reranking** -- Applies a cross-encoder reranking model after initial retrieval to improve relevance ordering. Adds latency but improves precision.

Hybrid search is generally the safest default for production workloads with mixed query types.

### Metadata Filtering

You can attach metadata to documents (via a companion `.metadata.json` file per source document) and filter retrieval results by metadata attributes at query time. This is essential for multi-tenant systems where you need to scope retrieval to a specific customer, department, or document category.

```json
{
  "metadataAttributes": {
    "department": { "value": "engineering", "type": "STRING" },
    "year": { "value": 2025, "type": "NUMBER" }
  }
}
```

At query time, pass a retrieval filter:

```python
response = bedrock_agent_runtime.retrieve_and_generate(
    input={"text": "What is our deployment policy?"},
    retrieveAndGenerateConfiguration={
        "knowledgeBaseConfiguration": {
            "knowledgeBaseId": kb_id,
            "modelArn": model_arn,
            "retrievalConfiguration": {
                "vectorSearchConfiguration": {
                    "filter": {
                        "equals": {"key": "department", "value": "engineering"}
                    }
                }
            }
        }
    }
)
```

---

## When to Use Bedrock Knowledge Bases vs Alternatives

| Criterion | Bedrock Knowledge Bases | Amazon Kendra | Custom Vector DB |
|-----------|------------------------|---------------|------------------|
| **Primary use case** | RAG over private docs with LLM generation | Enterprise search with ranking and facets | Full control over embeddings and retrieval |
| **Setup effort** | Low -- managed pipeline | Medium -- requires data source configuration and index tuning | High -- you build and operate everything |
| **Retrieval quality tuning** | Limited -- chunk size, search type, reranking | Extensive -- relevance tuning, custom synonyms, query suggestions | Full control |
| **Cost model** | Per-ingestion + per-query + vector store | Per-index-hour + per-query | Infrastructure cost (varies widely) |
| **Document freshness** | Batch ingestion (manual or scheduled) | Connectors with sync schedules | You control entirely |
| **LLM integration** | Built-in via RetrieveAndGenerate | Separate -- you wire Kendra results to an LLM yourself | Separate |
| **Best for** | Teams wanting managed RAG quickly | Teams needing search-first with optional RAG | Teams with specific retrieval quality requirements or existing vector DB investment |

**Choose Bedrock Knowledge Bases** when you want managed RAG with minimal infrastructure and your retrieval quality requirements are moderate. It is the fastest path from documents to a working RAG application.

**Choose Kendra** when search quality and ranking are the primary concern, you need features like faceted search or query suggestions, or you are building a search experience rather than a pure RAG pipeline.

**Choose a custom vector database** when you need fine-grained control over embedding models, chunking logic, index configuration, or retrieval algorithms. This path requires more engineering but gives you the most flexibility to optimize retrieval quality.

---

## Data Source Patterns

### S3-Backed Content

The most common pattern is syncing documents from S3. Organize your bucket with clear prefixes by content type or domain:

```
s3://my-knowledge-bucket/
  policies/
  technical-docs/
  runbooks/
```

Each prefix can map to a separate data source within the same knowledge base, allowing different chunking strategies per content type if needed.

### Structured vs Unstructured Content

Bedrock Knowledge Bases works best with unstructured text content: documentation, policies, reports, runbooks, and similar prose. It is not a replacement for structured data queries.

For structured data (database tables, CSV analytics, JSON records), consider:

- Using Amazon Athena or a relational database for direct queries rather than embedding structured data
- If you must include structured data, convert it to natural language descriptions before ingestion
- CSV files are supported but retrieval quality depends heavily on how well the content reads as natural language

> **Skill:** For provisioning S3 buckets as knowledge base data sources, use the `provision-s3-bucket` skill.

---

## IAM and Security

### Required Permissions

A Bedrock Knowledge Base needs an IAM service role with:

- `bedrock:InvokeModel` for the chosen embedding model
- `s3:GetObject` and `s3:ListBucket` for the data source bucket
- Permissions for the vector store (OpenSearch Serverless collection access, Aurora connection, etc.)
- `bedrock:Retrieve` and `bedrock:RetrieveAndGenerate` for the calling application

### Encryption

- Data at rest in the vector store is encrypted by default (AWS-managed keys or customer-managed KMS keys)
- S3 source documents should use SSE-S3 or SSE-KMS encryption
- Data in transit uses TLS

### Network Isolation

For sensitive workloads, use VPC endpoints for Bedrock and the vector store. OpenSearch Serverless collections can be configured with VPC access policies to prevent public access.

### Multi-Tenancy

Bedrock Knowledge Bases does not have built-in tenant isolation. For multi-tenant applications:

- Use metadata filtering to scope queries to a specific tenant
- For strict isolation, create separate knowledge bases per tenant (higher cost, simpler security model)
- Never rely solely on prompt instructions for tenant isolation -- always enforce it at the retrieval filter level

---

## Operational Considerations

### Ingestion Latency and Document Freshness

Ingestion is a batch process. After uploading new documents to S3, you must trigger an ingestion job. Depending on document volume, ingestion can take minutes to hours. There is no real-time or streaming ingestion.

For use cases requiring near-real-time document freshness, Bedrock Knowledge Bases may not be suitable. Consider a custom pipeline with incremental updates to your vector store.

### Cost Components

Cost comes from multiple dimensions:

- **Embedding model invocations** during ingestion (per-token pricing)
- **Vector store** -- OpenSearch Serverless has a minimum cost regardless of usage; customer-owned stores have their own pricing
- **Retrieve/RetrieveAndGenerate API calls** -- per-request pricing
- **LLM invocations** for the generation step (standard Bedrock model pricing)

The OpenSearch Serverless minimum cost (OCU-hours) can be surprising for low-traffic workloads. Evaluate whether the managed convenience justifies the floor cost versus a self-managed alternative.

### Monitoring

Use CloudWatch metrics for:

- Ingestion job status and duration
- Retrieve API latency and error rates
- Vector store health (OpenSearch Serverless metrics)

> **Skill:** For CloudWatch log querying and monitoring setup, use the `query-aws-logs` skill.

### Limits to Be Aware Of

- Maximum number of data sources per knowledge base (check current service quotas)
- Maximum document size for ingestion
- Maximum metadata attributes per document
- API throttling limits on Retrieve and RetrieveAndGenerate
- OpenSearch Serverless collection limits per account

These limits change over time. Always check the current AWS service quotas documentation before designing for scale.

---

## Common Mistakes

| Mistake | Why It Happens | What To Do Instead |
|---------|---------------|-------------------|
| Using default chunking without evaluation | Defaults seem convenient | Test multiple chunking strategies with representative queries; measure retrieval precision |
| Ignoring chunk overlap | Overlap seems wasteful | Without overlap, relevant information at chunk boundaries is lost; use 10-20% overlap |
| Embedding structured data as-is | CSV and JSON are technically supported | Convert structured data to natural language summaries, or query it directly via SQL |
| No metadata filtering for multi-tenant apps | Simpler to skip during prototyping | Always enforce tenant isolation via retrieval filters, not prompt instructions |
| Assuming real-time freshness | Mental model from database replication | Ingestion is batch; design for acceptable staleness or use a custom pipeline |
| Not monitoring retrieval quality | Hard to measure in production | Log retrieved chunks alongside user queries; periodically review relevance |
| Choosing managed OpenSearch Serverless without checking cost floor | Default option in console | Evaluate OCU-hour minimum cost against expected usage volume |

---

## References

- AWS Bedrock Knowledge Bases documentation (AWS docs)
- AWS Bedrock pricing page for current per-request and ingestion costs
- OpenSearch Serverless pricing for vector store cost estimation
