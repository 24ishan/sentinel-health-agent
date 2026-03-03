import os
os.environ["NO_PROXY"] = "localhost,127.0.0.1,192.168.1.6"
os.environ["OLLAMA_HOST"] = "http://192.168.1.6:11434"
from dotenv import load_dotenv
from langchain_community.document_loaders import PyPDFLoader
from langchain_text_splitters import RecursiveCharacterTextSplitter
from langchain_ollama import OllamaEmbeddings  # Note the cleaner import
from langchain_postgres.vectorstores import PGVector  # New library
load_dotenv()

# Configuration
DB_URL = "postgresql+psycopg://admin:password123@localhost:5432/health_agent"
COLLECTION_NAME = "medical_knowledge"
PDF_PATH = "data/tachycardia_1.pdf"


def ingest_medical_data():
    loader = PyPDFLoader(PDF_PATH)
    docs = loader.load()[:10]

    text_splitter = RecursiveCharacterTextSplitter(chunk_size=2000, chunk_overlap=200)
    chunks = text_splitter.split_documents(docs)

    # Talk to the PC (Ollama)
    embeddings = OllamaEmbeddings(model="llama3")

    print(f"💾 Storing {len(chunks)} chunks using the new PGVector library...")

    # NEW SYNTAX for langchain-postgres
    vector_store = PGVector.from_documents(
        embedding=embeddings,
        documents=chunks,
        collection_name=COLLECTION_NAME,
        connection=DB_URL,  # Key change: 'connection' instead of 'connection_string'
        use_jsonb=True,
    )
    print("✅ Ingestion complete!")


if __name__ == "__main__":
    ingest_medical_data()