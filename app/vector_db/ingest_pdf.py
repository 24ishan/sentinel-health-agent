import os
import hashlib
from langchain_postgres import PGVectorStore, PGEngine
from langchain_ollama import OllamaEmbeddings
from langchain_community.document_loaders import PyPDFLoader
from langchain_text_splitters import RecursiveCharacterTextSplitter
from app import setup_logging
logger = setup_logging()


class PostgresRAGManager:
    def __init__(self, engine, table_name: str, ollama_host: str):
        self.engine = engine
        self.table_name = table_name
        self.ollama_host = ollama_host
        self.vector_store = None
        self.embeddings = None

    @classmethod
    async def create(cls, engine, table_name, ollama_host):
        """FACTORY METHOD: Use this to create and initialize the manager."""
        instance = cls(engine, table_name, ollama_host)
        await instance._initialize()
        return instance

    async def _init_embeddings_with_retry(self) -> OllamaEmbeddings:
        max_retries = 3
        retry_delay = 5

        for attempt in range(1, max_retries + 1):
            try:
                logger.info(f"Connecting to Ollama ({self.ollama_host})... Attempt {attempt}/{max_retries}")
                embeddings = OllamaEmbeddings(
                    model="nomic-embed-text",
                    base_url=self.ollama_host
                )
                # Test connection
                embeddings.embed_query("test")
                logger.info("✅ Ollama connection successful")
                return embeddings
            except Exception as e:
                if attempt == max_retries:
                    logger.error(f"❌ Failed to connect to Ollama after {max_retries} attempts: {e}")
                    raise
                logger.warning(
                    f"⚠️ Ollama connection failed (attempt {attempt}/{max_retries}). Retrying in {retry_delay}s...")
                await asyncio.sleep(retry_delay)

    async def _initialize(self):
        """Handles the actual async database setup."""
        pg_engine = PGEngine.from_engine(self.engine)
        self.embeddings = await self._init_embeddings_with_retry()
        try:
            # 1. Initialize the table schema asynchronously
            await pg_engine.ainit_vectorstore_table(
                table_name=self.table_name,
                vector_size=768
            )
            logger.info(f"Table '{self.table_name}' initialized.")
        except Exception as e:
            if "already exists" in str(e).lower():
                logger.info(f"Table '{self.table_name}' already exists. Skipping creation.")
            else:
                logger.error(f"Unexpected error during table init: {e}")
                raise e

        # 2. Create the Vector Store instance asynchronously
        self.vector_store = await PGVectorStore.create(
            engine=pg_engine,
            table_name=self.table_name,
            embedding_service=self.embeddings,
            id_column="langchain_id"
        )

    def get_file_hash(self, file_path: str) -> str:
        """Generates a SHA-256 fingerprint of the file."""
        hasher = hashlib.sha256()
        with open(file_path, "rb") as f:
            while chunk := f.read(8192):
                hasher.update(chunk)
        return hasher.hexdigest()

    async def is_already_indexed(self, file_hash: str) -> bool:
        """Checks if the file hash exists in the metadata."""
        results = await self.vector_store.asimilarity_search(
            query="", # Empty query avoids heavy vector math
            k=1,
            filter={"file_hash": file_hash}
        )
        return len(results) > 0

    async def index_file(self, file_path: str):
        """Loads, chunks, and persists a PDF if it hasn't been indexed."""
        file_name = os.path.basename(file_path)
        file_hash = self.get_file_hash(file_path)

        # Deduplication Check
        if await self.is_already_indexed(file_hash):
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

            await self.vector_store.aadd_documents(chunks)
            logger.info(f"✅ Processing complete for {file_name}")
            logger.debug(f"🔐 File hash: {file_hash}")

            return {
                "status": "indexed",
                "chunks": len(chunks),
                "message": f"Successfully indexed {len(chunks)} chunks"
            }
        except Exception as e:
            logger.error(f"Failed to index {file_name}: {str(e)}", exc_info=True)
            return {"status": "failed", "chunks": 0, "error": str(e)}

    async def search(self, query: str, limit: int = 3):
        try:
            if not query or not query.strip():
                logger.warning("Empty search query")
                return []
            results = await self.vector_store.asimilarity_search(query, k=limit)
            logger.debug(f"🔍 Search returned {len(results)} results for: {query[:50]}...")
            return results
        except Exception as e:
            logger.error(f"Search failed: {e}", exc_info=True)
            return []


if __name__ == "__main__":

    async def main():
        from app.config import DATABASE_URL, VECTOR_TABLE_NAME, OLLAMA_HOST
        from sqlalchemy.ext.asyncio import create_async_engine

        # 1. Create the Async Engine
        engine = create_async_engine(
            DATABASE_URL,
            pool_pre_ping=True,
            pool_size=20,
            max_overflow=0
        )
        manager = await PostgresRAGManager.create(engine, VECTOR_TABLE_NAME, OLLAMA_HOST)

        # 3. Process File
        pdf_path = "data/tachycardia_1.pdf"
        if os.path.exists(pdf_path):
            await manager.index_file(pdf_path)

            # Test search
            results = await manager.search("What is tachycardia?")
            print(f"Search found {len(results)} results.")
        else:
            print(f"File not found: {pdf_path}")

    import asyncio
    asyncio.run(main())
