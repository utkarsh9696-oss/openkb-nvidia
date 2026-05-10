import os
import json
import re
import time
import requests as req_lib
from pathlib import Path
from flask import Flask, request, jsonify, send_from_directory
from flask_cors import CORS
from dotenv import load_dotenv

load_dotenv()

app = Flask(__name__, template_folder='templates')
CORS(app)

# Directories
UPLOAD_DIR = Path('uploads')
WIKI_DIR = Path('wiki')
SUMMARIES_DIR = WIKI_DIR / 'summaries'
CONCEPTS_DIR = WIKI_DIR / 'concepts'
GRAPH_DIR = WIKI_DIR / 'graph'
EXPLORATIONS_DIR = WIKI_DIR / 'explorations'

for d in [UPLOAD_DIR, SUMMARIES_DIR, CONCEPTS_DIR, GRAPH_DIR, EXPLORATIONS_DIR]:
    d.mkdir(parents=True, exist_ok=True)

MASTER_GRAPH_FILE = GRAPH_DIR / 'master_graph.json'

def call_nvidia(messages, max_tokens=2048):
    api_key = os.getenv('NVIDIA_API_KEY', '')
    if not api_key or api_key == 'nvapi-your-key-here':
        raise ValueError("NVIDIA API key not configured")
    url = 'https://integrate.api.nvidia.com/v1/chat/completions'
    headers = {
        'Authorization': f'Bearer {api_key}',
        'Content-Type': 'application/json'
    }
    payload = {
        'model': 'meta/llama-3.3-70b-instruct',
        'messages': messages,
        'max_tokens': max_tokens,
        'temperature': 0.2
    }
    response = req_lib.post(url, headers=headers, json=payload, timeout=120)
    response.raise_for_status()
    data = response.json()
    return data['choices'][0]['message']['content']

def load_master_graph():
    if MASTER_GRAPH_FILE.exists():
        with open(MASTER_GRAPH_FILE) as f:
            return json.load(f)
    return {'nodes': [], 'edges': []}

def save_master_graph(graph):
    with open(MASTER_GRAPH_FILE, 'w') as f:
        json.dump(graph, f, indent=2)

def clean_graph(graph):
    valid_ids = {n['id'] for n in graph.get('nodes', [])}
    clean_edges = []
    for e in graph.get('edges', []):
        src = e.get('source', '')
        tgt = e.get('target', '')
        if src in valid_ids and tgt in valid_ids:
            clean_edges.append(e)
    graph['edges'] = clean_edges
    return graph

def merge_graphs(master, new_graph, doc_name):
    existing_ids = {n['id'] for n in master['nodes']}
    for node in new_graph.get('nodes', []):
        node_id = node.get('id', '').strip()
        if not node_id:
            continue
        if node_id not in existing_ids:
            node['source_doc'] = doc_name
            master['nodes'].append(node)
            existing_ids.add(node_id)
    existing_edges = {(e['source'], e['target'], e.get('relationship','')) for e in master['edges']}
    for edge in new_graph.get('edges', []):
        src = edge.get('source', '')
        tgt = edge.get('target', '')
        key = (src, tgt, edge.get('relationship',''))
        if key not in existing_edges and src in existing_ids and tgt in existing_ids:
            edge['source_doc'] = doc_name
            master['edges'].append(edge)
            existing_edges.add(key)
    return master

def extract_json_from_text(text):
    try:
        return json.loads(text)
    except:
        pass
    match = re.search(r'\{[\s\S]*\}', text)
    if match:
        try:
            return json.loads(match.group())
        except:
            pass
    return None

def get_doc_list():
    docs = []
    indexed_names = set()
    for f in SUMMARIES_DIR.glob('*.md'):
        indexed_names.add(f.stem)
    for f in sorted(UPLOAD_DIR.iterdir()):
        if f.is_file() and f.suffix.lower() in ['.txt', '.pdf', '.md']:
            stem = f.stem
            docs.append({
                'name': f.name,
                'stem': stem,
                'indexed': stem in indexed_names,
                'size': f.stat().st_size,
                'path': str(f)
            })
    return docs

# Routes

@app.route('/')
def index():
    return send_from_directory('templates', 'index.html')

@app.route('/api/status')
def status():
    docs = get_doc_list()
    indexed = [d for d in docs if d['indexed']]
    graph = load_master_graph()
    api_key = os.getenv('NVIDIA_API_KEY', '')
    api_ready = bool(api_key and not api_key.startswith('nvapi-your'))
    wiki_pages = list(SUMMARIES_DIR.glob('*.md')) + list(CONCEPTS_DIR.glob('*.md'))
    return jsonify({
        'api_ready': api_ready,
        'total_docs': len(docs),
        'indexed_docs': len(indexed),
        'graph_nodes': len(graph['nodes']),
        'graph_edges': len(graph['edges']),
        'wiki_pages': len(wiki_pages),
        'explorations': len(list(EXPLORATIONS_DIR.glob('*.md')))
    })

@app.route('/api/documents')
def list_documents():
    return jsonify(get_doc_list())

@app.route('/api/documents/upload', methods=['POST'])
def upload_document():
    if 'file' not in request.files:
        return jsonify({'error': 'No file provided'}), 400
    f = request.files['file']
    if not f.filename:
        return jsonify({'error': 'Empty filename'}), 400
    allowed = {'.txt', '.pdf', '.md'}
    ext = Path(f.filename).suffix.lower()
    if ext not in allowed:
        return jsonify({'error': f'File type {ext} not supported. Use TXT, PDF, or MD.'}), 400
    save_path = UPLOAD_DIR / f.filename
    f.save(save_path)
    return jsonify({'success': True, 'filename': f.filename})

@app.route('/api/documents/delete', methods=['POST'])
def delete_document():
    data = request.json or {}
    filename = data.get('filename')
    if not filename:
        return jsonify({'error': 'filename required'}), 400
    doc_path = UPLOAD_DIR / filename
    if doc_path.exists():
        doc_path.unlink()
    stem = Path(filename).stem
    for f in [
        SUMMARIES_DIR / f'{stem}.md',
        GRAPH_DIR / f'{stem}.json',
    ]:
        if f.exists():
            f.unlink()
    master = {'nodes': [], 'edges': []}
    for gf in GRAPH_DIR.glob('*.json'):
        if gf.name == 'master_graph.json':
            continue
        try:
            with open(gf) as f:
                g = json.load(f)
            master = merge_graphs(master, g, gf.stem)
        except:
            pass
    save_master_graph(master)
    return jsonify({'success': True, 'filename': filename})

@app.route('/api/documents/index', methods=['POST'])
def index_document():
    data = request.json or {}
    filename = data.get('filename')
    if not filename:
        return jsonify({'error': 'filename required'}), 400
    doc_path = UPLOAD_DIR / filename
    if not doc_path.exists():
        return jsonify({'error': 'File not found'}), 404
    try:
        ext = doc_path.suffix.lower()
        if ext == '.pdf':
            try:
                import fitz
                doc = fitz.open(str(doc_path))
                content = ''
                for page in doc:
                    content += page.get_text()
                doc.close()
                if not content.strip():
                    content = doc_path.read_text(encoding='utf-8', errors='ignore')
            except ImportError:
                content = doc_path.read_text(encoding='utf-8', errors='ignore')
        else:
            content = doc_path.read_text(encoding='utf-8', errors='ignore')
    except Exception as e:
        return jsonify({'error': f'Could not read file: {e}'}), 500

    if len(content) > 12000:
        content = content[:12000] + '\n\n[Document truncated for processing]'

    doc_stem = doc_path.stem

    try:
        summary_prompt = f"""You are a knowledge base assistant. Read the following document and create a detailed wiki-style summary page.

Document Title: {filename}

Document Content:
{content}

Write a comprehensive wiki page with:
1. A brief overview paragraph
2. Key concepts section (bullet points)
3. Main topics covered (with short explanations)
4. Important relationships and connections between ideas
5. Key takeaways

Format it as clean markdown with headers (##) and bullet points."""

        summary_md = call_nvidia([{'role': 'user', 'content': summary_prompt}], max_tokens=1500)
        summary_file = SUMMARIES_DIR / f'{doc_stem}.md'
        summary_file.write_text(f'# {filename}\n\n{summary_md}', encoding='utf-8')

        graph_prompt = f"""You are a knowledge graph extraction system. Analyze this document and extract a structured knowledge graph.

Document:
{content}

Return ONLY valid JSON (no explanation, no markdown, no backticks) with this exact structure:
{{
  "nodes": [
    {{"id": "unique_id_no_spaces", "label": "Display Name", "type": "concept|entity|process|technology", "description": "One sentence description"}}
  ],
  "edges": [
    {{"source": "node_id_1", "target": "node_id_2", "relationship": "relationship label"}}
  ]
}}

Rules:
- Extract 10-20 most important nodes
- Node IDs must be lowercase with underscores, no spaces
- Types: concept (abstract idea), entity (specific thing/person/org), process (action/procedure), technology (tool/software/hardware)
- Edges should capture meaningful semantic relationships
- Extract 15-30 meaningful edges
- Return ONLY the JSON object, nothing else"""

        graph_raw = call_nvidia([{'role': 'user', 'content': graph_prompt}], max_tokens=2000)
        new_graph = extract_json_from_text(graph_raw)
        if not new_graph or 'nodes' not in new_graph:
            new_graph = {
                'nodes': [{'id': doc_stem, 'label': filename, 'type': 'concept', 'description': 'Document node'}],
                'edges': []
            }

        doc_graph_file = GRAPH_DIR / f'{doc_stem}.json'
        doc_graph_file.write_text(json.dumps(new_graph, indent=2), encoding='utf-8')

        master = load_master_graph()
        master = merge_graphs(master, new_graph, doc_stem)
        save_master_graph(master)

        return jsonify({
            'success': True,
            'filename': filename,
            'nodes_added': len(new_graph.get('nodes', [])),
            'edges_added': len(new_graph.get('edges', [])),
            'summary_saved': str(summary_file)
        })

    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/wiki/compile', methods=['POST'])
def compile_wiki():
    summaries = list(SUMMARIES_DIR.glob('*.md'))
    if not summaries:
        return jsonify({'error': 'No indexed documents found'}), 400
    all_summaries = ''
    for sf in summaries:
        all_summaries += f'\n\n### From: {sf.stem}\n'
        all_summaries += sf.read_text(encoding='utf-8')[:2000]
    try:
        prompt = f"""You are a knowledge base compiler. Based on these document summaries, identify 3-5 cross-cutting concepts or themes that appear across multiple documents and write a brief wiki page for each.

{all_summaries}

For each cross-cutting concept, return JSON array:
[
  {{"title": "Concept Title", "content": "Markdown content for this concept page (2-3 paragraphs)"}},
  ...
]

Return ONLY the JSON array, no other text."""

        result = call_nvidia([{'role': 'user', 'content': prompt}], max_tokens=2000)
        concepts = None
        match = re.search(r'\[[\s\S]*\]', result)
        if match:
            try:
                concepts = json.loads(match.group())
            except:
                pass
        pages_created = []
        if concepts:
            for c in concepts:
                title = c.get('title', 'Unnamed')
                content = c.get('content', '')
                safe_title = re.sub(r'[^\w\s-]', '', title).strip().replace(' ', '_')
                page_file = CONCEPTS_DIR / f'{safe_title}.md'
                page_file.write_text(f'# {title}\n\n{content}', encoding='utf-8')
                pages_created.append(title)
        return jsonify({'success': True, 'pages_created': pages_created})
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/wiki/pages')
def list_wiki_pages():
    pages = []
    for f in sorted(SUMMARIES_DIR.glob('*.md')):
        pages.append({'title': f.stem, 'type': 'summary', 'file': f.name})
    for f in sorted(CONCEPTS_DIR.glob('*.md')):
        pages.append({'title': f.stem.replace('_', ' '), 'type': 'concept', 'file': f.name})
    for f in sorted(EXPLORATIONS_DIR.glob('*.md')):
        pages.append({'title': f.stem.replace('_', ' '), 'type': 'exploration', 'file': f.name})
    return jsonify(pages)

@app.route('/api/wiki/page')
def get_wiki_page():
    title = request.args.get('title', '')
    ptype = request.args.get('type', 'summary')
    if not title:
        return jsonify({'error': 'title required'}), 400
    dirs = {'summary': SUMMARIES_DIR, 'concept': CONCEPTS_DIR, 'exploration': EXPLORATIONS_DIR}
    base_dir = dirs.get(ptype, SUMMARIES_DIR)
    page_file = base_dir / f'{title}.md'
    if not page_file.exists():
        page_file = base_dir / f'{title.replace(" ", "_")}.md'
    if not page_file.exists():
        return jsonify({'error': 'Page not found'}), 404
    content = page_file.read_text(encoding='utf-8')
    return jsonify({'title': title, 'content': content, 'type': ptype})

@app.route('/api/graph')
def get_graph():
    graph = load_master_graph()
    graph = clean_graph(graph)
    return jsonify(graph)

@app.route('/api/search', methods=['POST'])
def search():
    data = request.json or {}
    query = data.get('query', '').strip()
    if not query:
        return jsonify({'error': 'query required'}), 400
    context_parts = []
    for sf in sorted(SUMMARIES_DIR.glob('*.md'))[:5]:
        context_parts.append(f'=== {sf.stem} ===\n' + sf.read_text(encoding='utf-8')[:1500])
    graph = load_master_graph()
    if graph['nodes']:
        graph_summary = 'Knowledge Graph Nodes: ' + ', '.join(
            f"{n['label']} ({n['type']})" for n in graph['nodes'][:30]
        )
        context_parts.append(graph_summary)
    context = '\n\n'.join(context_parts)
    if not context:
        return jsonify({'error': 'No documents indexed yet. Please index some documents first.'}), 400
    try:
        prompt = f"""You are a knowledge base assistant. Answer the user's question based on the indexed documents below.

KNOWLEDGE BASE:
{context}

USER QUESTION: {query}

Provide a comprehensive, well-structured answer. Include:
1. A direct answer to the question
2. Supporting details from the documents
3. Related concepts from the knowledge graph
4. Mention which documents contain relevant information

If the question cannot be answered from the knowledge base, say so clearly."""

        answer = call_nvidia([{'role': 'user', 'content': prompt}], max_tokens=1500)
        ts = int(time.time())
        safe_q = re.sub(r'[^\w\s]', '', query)[:40].strip().replace(' ', '_')
        exp_file = EXPLORATIONS_DIR / f'{safe_q}_{ts}.md'
        exp_file.write_text(
            f'# Query: {query}\n\n**Date:** {time.strftime("%Y-%m-%d %H:%M:%S")}\n\n## Answer\n\n{answer}',
            encoding='utf-8'
        )
        query_lower = query.lower()
        relevant_nodes = [
            n for n in graph['nodes']
            if query_lower in n.get('label', '').lower() or
               query_lower in n.get('description', '').lower() or
               any(word in n.get('label', '').lower() for word in query_lower.split() if len(word) > 3)
        ][:5]
        sources = [sf.stem for sf in SUMMARIES_DIR.glob('*.md')]
        return jsonify({
            'answer': answer,
            'sources': sources,
            'relevant_nodes': relevant_nodes,
            'exploration_saved': exp_file.name
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500

if __name__ == '__main__':
    print("=" * 50)
    print("  OpenKB-NVIDIA Knowledge Base")
    print("=" * 50)
    api_key = os.getenv('NVIDIA_API_KEY', '')
    if not api_key or api_key == 'nvapi-your-key-here':
        print("  WARNING: Add your NVIDIA API key to .env")
        print("  Get a free key at https://build.nvidia.com")
    else:
        print("  NVIDIA API key loaded")
    print("  Open http://localhost:5000")
    print("=" * 50)
    port = int(os.environ.get('PORT', 5000))
    app.run(debug=False, host='0.0.0.0', port=port)