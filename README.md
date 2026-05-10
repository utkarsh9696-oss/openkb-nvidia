# OpenKB-NVIDIA — AI Knowledge Graph

A searchable AI knowledge base with interactive **knowledge graph visualization**, powered by NVIDIA NIM (LLaMA 3.3 70B). Built as a prototype demonstrating the "graphify approach" — representing knowledge as a graph of interconnected concepts rather than flat document chunks.

---

## Features

- **📄 Document Upload** — Drop TXT, PDF, or Markdown files
- **⬡ Knowledge Graph** — D3.js force-directed graph with clickable nodes, zoom/pan
- **🤖 AI Indexing** — NVIDIA LLaMA extracts concepts (nodes) and relationships (edges)
- **🔍 Semantic Search** — Plain-English queries answered from your documents
- **📖 Wiki Pages** — Auto-generated summaries and cross-document concept pages
- **💾 Explorations** — Every search result saved as a wiki page

---

## Quick Start

### 1. Get a free NVIDIA API key

Go to [https://build.nvidia.com](https://build.nvidia.com), create an account, and get a free API key starting with `nvapi-`.

### 2. Add your API key

Edit `.env`:
```
NVIDIA_API_KEY=nvapi-your-actual-key-here
```

### 3. Install dependencies
```bash
pip install -r requirements.txt
```

### 4. Run the server
```bash
python app.py
```

### 5. Open the app
Navigate to [http://localhost:5000](http://localhost:5000)

---

## Usage Flow

1. **Add Docs tab** → Upload `.txt` or `.pdf` files
2. Click **Index →** next to each document — AI extracts the knowledge graph
3. **Graph tab** → Explore the interactive concept graph, click nodes
4. **Search tab** → Ask questions in plain English
5. **Wiki tab** → Browse generated summaries and concept pages
6. **Dashboard** → Click "Compile Cross-Doc Wiki" to generate cross-document concept pages

---

## Architecture

```
User Upload
    ↓
Flask Backend (app.py)
    ↓
NVIDIA NIM API (meta/llama-3.3-70b-instruct)
    ↙         ↘
Wiki Summary   Knowledge Graph JSON
(.md files)    (nodes + edges)
    ↓               ↓
Wiki Browser    D3.js Force Graph
                    ↓
              Search Context
```

### Why Graph over RAG?

Traditional RAG treats documents as isolated chunks. A knowledge graph captures **relationships** — "Process Management **uses** CPU Scheduling", "Neural Networks **is-a** Deep Learning technique". You can traverse connections: *"What concepts link Process Management to File Systems?"*

### Why No Vector DB?

Following the OpenKB philosophy: the LLM reads structured wiki markdown + graph JSON directly. Simpler architecture, no infrastructure overhead, and the graph topology itself encodes semantic relationships.

---

## Project Structure

```
openkb-nvidia/
├── app.py                  # Flask backend (all API routes)
├── requirements.txt
├── .env                    # NVIDIA_API_KEY=nvapi-xxx
├── templates/
│   └── index.html          # Full frontend (D3.js graph + tabs)
├── uploads/                # User documents
│   ├── operating_systems_overview.txt   # Sample doc 1
│   └── machine_learning_fundamentals.txt # Sample doc 2
└── wiki/
    ├── summaries/           # Per-document AI summaries (.md)
    ├── concepts/            # Cross-document concept pages (.md)
    ├── graph/               # Graph JSON (per-doc + master)
    └── explorations/        # Saved search results (.md)
```

---

## API Endpoints

| Method | Path | Description |
|--------|------|-------------|
| GET | `/` | Serve frontend |
| GET | `/api/status` | Counts + API ready bool |
| GET | `/api/documents` | List uploads with indexed status |
| POST | `/api/documents/upload` | Save uploaded file |
| POST | `/api/documents/index` | AI extraction → summary + graph |
| POST | `/api/wiki/compile` | Cross-document concept pages |
| GET | `/api/wiki/pages` | List all wiki pages |
| GET | `/api/wiki/page?title=X` | Get single page content |
| GET | `/api/graph` | Full master graph `{nodes, edges}` |
| POST | `/api/search` | Semantic search, returns answer + sources |

---

## Tech Stack

- **Backend**: Python 3.10+ / Flask 3.0
- **AI**: NVIDIA NIM API — `meta/llama-3.3-70b-instruct`
- **Graph Viz**: D3.js v7 force-directed layout
- **Frontend**: Vanilla HTML/CSS/JS (no framework)
- **Storage**: Local filesystem (no database)
