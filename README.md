# GraphRAG

A powerful implementation of Retrieval Augmented Generation (RAG) using knowledge graphs built with Neo4j for enhanced context-aware retrieval and generation. This project focuses on analyzing sales call transcripts and PDF documents to extract valuable insights and relationships.

## 📋 Overview

GraphRAG combines the power of knowledge graphs with large language models to provide context-rich retrieval and generation capabilities. This implementation specializes in:

1. **Sales Call Analysis**: Extracts entities, relationships, and sales insights from call transcripts
2. **Document Knowledge Graphs**: Builds knowledge graphs from PDF documents
3. **Advanced Query Capabilities**: Provides natural language querying of complex relationships

## 🛠️ Features

- **Knowledge Graph Construction**:
  - Convert call transcripts to structured knowledge graphs
  - Extract entities and relationships from PDF documents
  - Validate and score extraction quality

- **Graph-based RAG**:
  - Leverage Neo4j's graph database for context-aware retrieval
  - Combine LLM capabilities with graph structure for enhanced responses
  - Support for complex relationship queries

- **Sales Intelligence**:
  - Track customer pain points, objections, and buying signals
  - Map customer interactions to ideal customer profiles (ICP)
  - Analyze call outcomes and performance

## 🔧 Installation

1. Clone the repository:
   ```bash
   git clone https://github.com/MushafMughal/GraphRAG.git
   cd GraphRAG
   ```

2. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```

3. Set up environment variables in a `.env` file:
   ```
   NEO4J_URL=bolt://localhost:7687
   NEO4J_USERNAME=neo4j
   NEO4J_PASSWORDD=your_password
   NEO4J_DATABASE1=call_knowledge_graph
   NEO4J_DATABASE2=pdf_knowledge_graph
   OPENAI_API_KEY=your_openai_api_key
   ```

## 📝 Usage

### Main Notebooks

The project includes three main Jupyter notebooks:

1. **Construct_knowledgeGraphs_Calls.ipynb**: Constructs knowledge graphs from call transcripts by extracting entities, relationships, and sales insights.
   
2. **Construct_knowledgeGraphs_Pdfs.ipynb**: Builds knowledge graphs from PDF documents, allowing you to query and analyze document content through graph relationships.

3. **graphRAG.ipynb**: Main notebook for querying and retrieving information using the GraphRAG approach, combining knowledge graphs with language models.

### Data Structure

- **Call Transcripts**: Stored in `call transcripts/` directory
- **Call JSON Data**: Processed call data in `call outputs/` directory
- **PDF Documents**: Source PDFs in `pdfs/` directory

## 🧩 Project Structure

```
GraphRAG/
├── Construct_knowledgeGraphs_Calls.ipynb   # Call transcript to knowledge graph
├── Construct_knowledgeGraphs_Pdfs.ipynb    # PDF to knowledge graph
├── graphRAG.ipynb                          # Main GraphRAG querying notebook
├── requirements.txt                        # Python dependencies
├── call outputs/                           # Processed call data
│   └── call_*/                             # Individual call data
├── call transcripts/                       # Raw call transcripts
└── pdfs/                                   # Source PDF documents
```

## 🔍 Example Queries

```python
# Connect to the knowledge graph
callsgraph = Neo4jGraph(
    url=NEO4J_URL,
    username=NEO4J_USERNAME,
    password=NEO4J_PASSWORDD,
    database=NEO4J_DATABASE1
)

# Create a question-answering chain
callschain = GraphCypherQAChain.from_llm(
    graph=callsgraph, 
    llm=ChatOpenAI(model="gpt-5-mini", temperature=0),
    verbose=True
)

# Query the knowledge graph
response = callschain.invoke({
    "query": "What are the common objections raised in the last 3 calls?"
})
print(response['result'])
```

## 🔗 Dependencies

Key libraries used in this project:
- langchain
- langchain-neo4j
- langchain-openai
- neo4j
- pydantic
- openai
- google-genai