import os
import sys
import glob
import re
import yaml
import tiktoken
from typing import List, Dict, Any, Tuple
from pypdf import PdfReader
from dotenv import load_dotenv

# Add current folder to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from embedder import Embedder

# Load environment variables from .env in project root or current dir
load_dotenv(os.path.join(os.path.dirname(__file__), "..", ".env"))
load_dotenv(os.path.join(os.path.dirname(__file__), ".env"))

def load_config() -> Dict[str, Any]:
    config_path = os.path.join(os.path.dirname(__file__), "config.yaml")
    with open(config_path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)

def clean_id_str(text: str) -> str:
    """Sanitize string for Pinecone vector IDs (ASCII alphanumeric, dashes, underscores)."""
    return re.sub(r'[^a-zA-Z0-9_\-]', '_', text)

def chunk_page_text(
    text: str,
    tokenizer: Any,
    chunk_size: int = 500,
    chunk_overlap: int = 50
) -> List[str]:
    """Chunk text using fixed token size and overlap."""
    tokens = tokenizer.encode(text)
    if not tokens:
        return []

    if len(tokens) <= chunk_size:
        return [text.strip()]

    chunks = []
    step = max(1, chunk_size - chunk_overlap)
    start = 0
    while start < len(tokens):
        end = min(start + chunk_size, len(tokens))
        chunk_token_slice = tokens[start:end]
        chunk_text = tokenizer.decode(chunk_token_slice).strip()
        if chunk_text:
            chunks.append(chunk_text)
        if end >= len(tokens):
            break
        start += step

    return chunks

def ingest_pdfs() -> Dict[str, Any]:
    config = load_config()
    
    # 1. Environment & API Keys
    pinecone_api_key = os.getenv("PINECONE_API_KEY")
    if not pinecone_api_key:
        raise ValueError(
            "PINECONE_API_KEY is not set in environment or .env file! "
            "Please set PINECONE_API_KEY in .env before running ingestion."
        )

    # 2. Config parameters
    chunk_size = config.get("chunking", {}).get("chunk_size", 500)
    chunk_overlap = config.get("chunking", {}).get("chunk_overlap", 50)
    encoding_name = config.get("chunking", {}).get("encoding_name", "cl100k_base")
    
    emb_cfg = config.get("embedding", {})
    embed_model_name = emb_cfg.get("model_name", "BAAI/bge-small-en-v1.5")
    dimension = emb_cfg.get("dimension", 384)
    metric = emb_cfg.get("metric", "cosine")
    
    pc_cfg = config.get("pinecone", {})
    index_name = os.getenv("PINECONE_INDEX_NAME", pc_cfg.get("index_name", "disaster-rag"))
    cloud = pc_cfg.get("cloud", "aws")
    region = pc_cfg.get("region", "us-east-1")
    batch_size = pc_cfg.get("batch_size", 100)

    # 3. Resolve PDFs directory
    raw_pdf_dir = config.get("paths", {}).get("pdfs_dir", "../pdfs")
    pdf_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), raw_pdf_dir))

    if not os.path.exists(pdf_dir):
        print(f"PDF directory does not exist: {pdf_dir}")
        return {"num_pdfs": 0, "total_pages": 0, "scanned_pages": 0, "total_chunks": 0, "index_vector_count": 0}

    pdf_files = sorted(glob.glob(os.path.join(pdf_dir, "*.pdf")))
    num_pdfs = len(pdf_files)
    print(f"\n--- Found {num_pdfs} PDF(s) in {pdf_dir} ---")

    if num_pdfs == 0:
        print("No PDFs found in directory to ingest.")
        return {"num_pdfs": 0, "total_pages": 0, "scanned_pages": 0, "total_chunks": 0, "index_vector_count": 0}

    # Initialize tokenizer and embedder
    tokenizer = tiktoken.get_encoding(encoding_name)
    embedder = Embedder(model_name=embed_model_name, device=emb_cfg.get("device", "cpu"))

    all_chunks_to_upsert: List[Dict[str, Any]] = []
    total_pages_count = 0
    scanned_pages_log: List[Tuple[str, int]] = []

    for pdf_path in pdf_files:
        filename = os.path.basename(pdf_path)
        clean_file_prefix = clean_id_str(filename)
        try:
            reader = PdfReader(pdf_path)
            num_pages = len(reader.pages)
            print(f"Processing '{filename}': {num_pages} pages")

            for page_idx, page in enumerate(reader.pages):
                page_num = page_idx + 1  # 1-indexed
                total_pages_count += 1
                try:
                    text = page.extract_text() or ""
                except Exception as extract_err:
                    text = ""
                    print(f"  [Error] Failed extracting text from {filename} page {page_num}: {extract_err}")

                clean_text = text.strip()
                if not clean_text:
                    scanned_pages_log.append((filename, page_num))
                    print(f"  [NOTICE] Page {page_num} of '{filename}' has no extractable text (likely scanned or image-based).")
                    continue

                chunks = chunk_page_text(clean_text, tokenizer, chunk_size, chunk_overlap)
                for chunk_idx, chunk_content in enumerate(chunks):
                    # Deterministic ID: filename__p{page}__c{chunk_idx}
                    chunk_id = f"{clean_file_prefix}__p{page_num}__c{chunk_idx}"
                    all_chunks_to_upsert.append({
                        "id": chunk_id,
                        "text": chunk_content,
                        "metadata": {
                            "source_file": filename,
                            "page": page_num,
                            "chunk_id": chunk_id,
                            "chunk_text": chunk_content
                        }
                    })

        except Exception as e:
            print(f"  [Error] Failed reading '{filename}': {e}")

    total_chunks = len(all_chunks_to_upsert)
    print(f"\nTotal PDFs: {num_pdfs}")
    print(f"Total Pages scanned: {total_pages_count}")
    print(f"Pages with no extractable text (logged): {len(scanned_pages_log)}")
    print(f"Total Chunks created: {total_chunks}")

    if total_chunks == 0:
        print("No text chunks extracted. Skipping Pinecone upsert.")
        return {
            "num_pdfs": num_pdfs,
            "total_pages": total_pages_count,
            "scanned_pages": len(scanned_pages_log),
            "total_chunks": 0,
            "index_vector_count": 0
        }

    # 4. Connect to Pinecone
    from pinecone import Pinecone, ServerlessSpec
    pc = Pinecone(api_key=pinecone_api_key)

    existing_indexes = [idx["name"] for idx in pc.list_indexes()]
    if index_name not in existing_indexes:
        print(f"Creating Pinecone index '{index_name}' (dim={dimension}, metric={metric})...")
        pc.create_index(
            name=index_name,
            dimension=dimension,
            metric=metric,
            spec=ServerlessSpec(cloud=cloud, region=region)
        )
    else:
        print(f"Using existing Pinecone index '{index_name}'.")

    index = pc.Index(index_name)

    # 5. Embed & Upsert in batches
    print(f"Generating embeddings with {embed_model_name} and upserting in batches of {batch_size}...")
    for i in range(0, total_chunks, batch_size):
        batch = all_chunks_to_upsert[i : i + batch_size]
        batch_texts = [b["text"] for b in batch]
        batch_embeddings = embedder.embed_texts(batch_texts)

        vectors_to_upsert = []
        for b, emb in zip(batch, batch_embeddings):
            vectors_to_upsert.append({
                "id": b["id"],
                "values": emb,
                "metadata": b["metadata"]
            })

        index.upsert(vectors=vectors_to_upsert)
        print(f"  Upserted {min(i + batch_size, total_chunks)} / {total_chunks} chunks...")

    # Fetch stats
    stats = index.describe_index_stats()
    vector_count = stats.get("total_vector_count", total_chunks)
    print(f"\n=======================================================")
    print(f"INGESTION COMPLETE:")
    print(f"  Number of PDFs:            {num_pdfs}")
    print(f"  Total pages processed:     {total_pages_count}")
    print(f"  Scanned/empty pages:       {len(scanned_pages_log)}")
    print(f"  Total chunks created:      {total_chunks}")
    print(f"  Pinecone index vector count: {vector_count}")
    print(f"=======================================================\n")

    return {
        "num_pdfs": num_pdfs,
        "total_pages": total_pages_count,
        "scanned_pages": len(scanned_pages_log),
        "total_chunks": total_chunks,
        "index_vector_count": vector_count
    }

if __name__ == "__main__":
    ingest_pdfs()
