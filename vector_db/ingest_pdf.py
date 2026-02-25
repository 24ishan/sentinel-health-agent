import os
from dotenv import load_dotenv
from langchain_community.document_loaders import PyPDFLoader
from langchain_text_splitters import RecursiveCharacterTextSplitter
from langchain_community.embeddings import OllamaEmbeddings
from langchain_community.vectorstores import PGVector

load_dotenv()

# Configuration
DB_URL = os.getenv("DATABASE_URL") # Ensure this is in your .env
COLLECTION_NAME = "medical_knowledge"
PDF_PATH = "data/tachycardia_1.pdf"

def ingest_medical_data():
    # 1. Load PDF
    print(f"📄 Loading {PDF_PATH}...")
    loader = PyPDFLoader(PDF_PATH)
    docs = loader.load()

    # 2. Split text into chunks (Senior Tip: Overlap helps maintain context)
    print("✂️ Splitting text into chunks...")
    text_splitter = RecursiveCharacterTextSplitter(chunk_size=1000, chunk_overlap=100)
    chunks = text_splitter.split_documents(docs)

    # 3. Initialize Embeddings (Using Ollama locally for privacy)
    # Make sure you have Ollama running: 'ollama run llama3'
    embeddings = OllamaEmbeddings(model="llama3")

    # 4. Store in pgvector
    print(f"💾 Storing {len(chunks)} chunks in pgvector...")
    PGVector.from_documents(
        embedding=embeddings,
        documents=chunks,
        collection_name=COLLECTION_NAME,
        connection_string=DB_URL,
        use_jsonb=True,
    )
    print("✅ Ingestion complete!")

if __name__ == "__main__":
    ingest_medical_data()