import os
import hashlib
from langchain_postgres import PGEngine, PGVectorStore
from langchain_ollama import OllamaEmbeddings
from langchain_community.document_loaders import PyPDFLoader
from langchain_text_splitters import RecursiveCharacterTextSplitter
from app import setup_logging
logger = setup_logging()


class PostgresRAGManager:
    def __init__(self, engine: PGEngine, table_name: str, ollama_host: str):
        self.engine = engine
        self.table_name = table_name
        self.ollama_host = ollama_host

        self.embeddings = OllamaEmbeddings(
            model="nomic-embed-text",
            base_url=self.ollama_host
        )

        try:
            self.engine.init_vectorstore_table(
                table_name=self.table_name,
                vector_size=768,
                id_column="langchain_id"
            )
            logger.info(f"Table '{self.table_name}' initialized.")
        except Exception as e:
            if "already exists" not in str(e).lower():
                logger.error(f"Critical DB Init Error: {e}")
                raise

        self.vector_store = PGVectorStore.create_sync(
            engine=self.engine,
            embedding_service=self.embeddings,
            table_name=self.table_name,
            id_column="langchain_id"
        )

    def get_file_hash(self, file_path: str) -> str:
        """Generates a SHA-256 fingerprint of the file."""
        hasher = hashlib.sha256()
        with open(file_path, "rb") as f:
            while chunk := f.read(8192):
                hasher.update(chunk)
        return hasher.hexdigest()

    def is_already_indexed(self, file_hash: str) -> bool:
        """Checks if the file hash exists in the metadata."""
        results = self.vector_store.similarity_search(
            query="", # Empty query avoids heavy vector math
            k=1,
            filter={"file_hash": file_hash}
        )
        return len(results) > 0

    def index_file(self, file_path: str):
        """Loads, chunks, and persists a PDF if it hasn't been indexed."""
        file_name = os.path.basename(file_path)
        file_hash = self.get_file_hash(file_path)

        # Deduplication Check
        if self.is_already_indexed(file_hash):
            logger.info(f"Skipping '{file_name}': Already present in database.")
            return

        logger.info(f"Indexing new document: {file_name}")

        try:
            # Load PDF
            loader = PyPDFLoader(file_path)
            docs = loader.load()[:2] #TODO Remove this limit after testing to index the entire document

            # Split into semantic chunks
            text_splitter = RecursiveCharacterTextSplitter(
                chunk_size=1000,
                chunk_overlap=100,
                add_start_index=True
            )
            chunks = text_splitter.split_documents(docs)

            # Enrich metadata with the hash for future checks
            for chunk in chunks:
                chunk.metadata.update({
                    "file_hash": file_hash,
                    "source": file_name
                })

            self.vector_store.add_documents(chunks)
            logger.info(f"Successfully stored {len(chunks)} chunks in pgvector.")

        except Exception as e:
            logger.error(f"Failed to index {file_name}: {str(e)}")

    def search(self, query: str, limit: int = 3):
        """Simple retrieval function for testing."""
        return self.vector_store.similarity_search(query, k=limit)


if __name__ == "__main__":
    from app.config import DATABASE_URL,VECTOR_TABLE_NAME,OLLAMA_HOST

    engine = PGEngine.from_connection_string(DATABASE_URL)
    manager = PostgresRAGManager(engine,VECTOR_TABLE_NAME,OLLAMA_HOST)

    # Optional: Reset everything if you have old, broken tables
    # manager.engine.drop_tables()

    pdf_path = "data/tachycardia_1.pdf"
    if os.path.exists(pdf_path):
        manager.index_file(pdf_path)
    else:
        print("Please provide a valid PDF path to test.")
