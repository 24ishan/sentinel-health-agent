"""
PostgreSQL-backed RAG ingestion manager.

Loads a PDF, splits it into semantic chunks, and stores the embeddings
in a PGVectorStore table.  Supports deduplication via a SHA-256 file hash
stored in each chunk's metadata.

Usage:
    manager = await PostgresRAGManager.create(engine, table_name, ollama_host)
    await manager.index_file("path/to/file.pdf")
"""
import asyncio
import hashlib
import os

from langchain_community.document_loaders import PyPDFLoader
from langchain_ollama import OllamaEmbeddings
from langchain_postgres import PGEngine, PGVectorStore
from langchain_text_splitters import RecursiveCharacterTextSplitter

from app import setup_logging
from app.utils.config import MEDICAL_EMBEDDING_MODEL

logger = setup_logging()

# Maximum number of PDF pages to index in a single run.
# Increase this value (or set to None) to index full documents.
MAX_PDF_PAGES: int | None = None


class PostgresRAGManager:
    """
    Manages PDF ingestion into a PostgreSQL vector store.

    Use the `create` class method (factory) to obtain an initialised instance
    because the setup involves async I/O.

    Attributes:
        engine:       Raw SQLAlchemy async engine passed in from outside.
        table_name:   Name of the pgvector table to store embeddings.
        ollama_host:  Base URL of the Ollama service.
        vector_store: Initialised PGVectorStore (set after _initialize).
        embeddings:   OllamaEmbeddings instance.
    """

    def __init__(self, engine, table_name: str, ollama_host: str) -> None:
        self.engine = engine
        self.table_name = table_name
        self.ollama_host = ollama_host
        self.vector_store: PGVectorStore | None = None
        self.embeddings: OllamaEmbeddings | None = None

    # ── Factory ───────────────────────────────────────────────────────────

    @classmethod
    async def create(cls, engine, table_name: str, ollama_host: str) -> "PostgresRAGManager":
        """
        Create and fully initialise a PostgresRAGManager instance.

        Args:
            engine:      Async SQLAlchemy engine (e.g. from database.py).
            table_name:  Name of the pgvector embeddings table.
            ollama_host: Base URL of the Ollama embedding service.

        Returns:
            Fully initialised PostgresRAGManager.
        """
        instance = cls(engine, table_name, ollama_host)
        await instance._initialize()
        return instance

    # ── Initialisation helpers ────────────────────────────────────────────

    async def _init_embeddings_with_retry(self) -> OllamaEmbeddings:  # type: ignore[return]
        """
        Connect to Ollama embeddings with up to 3 retries.

        Raises:
            Exception: If all retry attempts fail.
        """
        max_retries = 3
        retry_delay = 5
        last_exc: Exception = RuntimeError("Ollama connection failed")

        for attempt in range(1, max_retries + 1):
            try:
                logger.info(
                    f"Connecting to Ollama ({self.ollama_host})... "
                    f"Attempt {attempt}/{max_retries}"
                )
                embeddings = OllamaEmbeddings(
                    model=MEDICAL_EMBEDDING_MODEL,
                    base_url=self.ollama_host,
                )
                # Smoke-test the connection
                embeddings.embed_query("test")
                logger.info("✅ Ollama embeddings connection successful")
                return embeddings
            except Exception as exc:
                last_exc = exc
                if attempt == max_retries:
                    logger.error(
                        f"❌ Failed to connect to Ollama after {max_retries} attempts: {exc}"
                    )
                    break
                logger.warning(
                    f"⚠️ Ollama connection failed (attempt {attempt}/{max_retries}). "
                    f"Retrying in {retry_delay}s..."
                )
                await asyncio.sleep(retry_delay)

        raise last_exc

    async def _initialize(self) -> None:
        """Set up the pgvector table and initialise the vector store."""
        pg_engine = PGEngine.from_engine(self.engine)
        self.embeddings = await self._init_embeddings_with_retry()

        try:
            # Create the vector table if it does not exist
            await pg_engine.ainit_vectorstore_table(
                table_name=self.table_name,
                vector_size=768,
            )
            logger.info(f"Table '{self.table_name}' initialised.")
        except Exception as exc:
            if "already exists" in str(exc).lower():
                logger.info(f"Table '{self.table_name}' already exists. Skipping creation.")
            else:
                logger.error(f"Unexpected error during table init: {exc}")
                raise

        self.vector_store = await PGVectorStore.create(
            engine=pg_engine,
            table_name=self.table_name,
            embedding_service=self.embeddings,
            id_column="langchain_id",
        )

    # ── Deduplication ─────────────────────────────────────────────────────

    @staticmethod
    def get_file_hash(file_path: str) -> str:
        """
        Generate a SHA-256 fingerprint for a file.

        Args:
            file_path: Path to the file.

        Returns:
            Hex-encoded SHA-256 digest.
        """
        hasher = hashlib.sha256()
        with open(file_path, "rb") as fh:
            while chunk := fh.read(8192):
                hasher.update(chunk)
        return hasher.hexdigest()

    async def is_already_indexed(self, file_hash: str) -> bool:
        """
        Check whether a file (by hash) has already been indexed.

        Args:
            file_hash: SHA-256 hex digest of the file.

        Returns:
            True if the hash is found in the vector store metadata.
        """
        results = await self.vector_store.asimilarity_search(
            query="",  # Empty query skips heavy vector math
            k=1,
            filter={"file_hash": file_hash},
        )
        return len(results) > 0

    # ── Indexing ──────────────────────────────────────────────────────────

    async def index_file(self, file_path: str) -> dict:
        """
        Load, chunk, and persist a PDF if it has not already been indexed.

        Args:
            file_path: Path to the PDF file to index.

        Returns:
            dict with keys: status, chunks, message (or error).
        """
        file_name = os.path.basename(file_path)
        file_hash = self.get_file_hash(file_path)

        if await self.is_already_indexed(file_hash):
            logger.info(f"Skipping '{file_name}': already present in database.")
            return {"status": "skipped", "chunks": 0, "message": "Already indexed"}

        logger.info(f"Indexing new document: {file_name}")

        try:
            loader = PyPDFLoader(file_path)
            docs = loader.load()

            # Optionally limit pages (controlled by MAX_PDF_PAGES constant)
            if MAX_PDF_PAGES is not None:
                docs = docs[:MAX_PDF_PAGES]

            text_splitter = RecursiveCharacterTextSplitter(
                chunk_size=1000,
                chunk_overlap=100,
                add_start_index=True,
            )
            chunks = text_splitter.split_documents(docs)

            # Tag each chunk with hash + source for deduplication and tracing
            for chunk in chunks:
                chunk.metadata.update({"file_hash": file_hash, "source": file_name})

            await self.vector_store.aadd_documents(chunks)
            logger.info(f"✅ Indexed {len(chunks)} chunks from {file_name}")
            logger.debug(f"🔐 File hash: {file_hash}")

            return {
                "status": "indexed",
                "chunks": len(chunks),
                "message": f"Successfully indexed {len(chunks)} chunks",
            }
        except Exception as exc:
            logger.error(f"Failed to index {file_name}: {exc}", exc_info=True)
            return {"status": "failed", "chunks": 0, "error": str(exc)}

    # ── Search ────────────────────────────────────────────────────────────

    async def search(self, query: str, limit: int = 3) -> list:
        """
        Perform a similarity search against the vector store.

        Args:
            query: Natural-language search query.
            limit: Maximum number of results to return.

        Returns:
            List of matching Document objects (empty list on error or empty query).
        """
        if not query or not query.strip():
            logger.warning("Empty search query — returning empty results")
            return []
        try:
            results = await self.vector_store.asimilarity_search(query, k=limit)
            logger.debug(f"🔍 Search returned {len(results)} results for: {query[:50]}...")
            return results
        except Exception as exc:
            logger.error(f"Search failed: {exc}", exc_info=True)
            return []


# ---------------------------------------------------------------------------
# Standalone script entry-point for manual ingestion
# ---------------------------------------------------------------------------

if __name__ == "__main__":

    async def _main() -> None:
        from sqlalchemy.ext.asyncio import create_async_engine

        from app.utils.config import DATABASE_URL, OLLAMA_HOST, VECTOR_TABLE_NAME

        _engine = create_async_engine(DATABASE_URL, pool_pre_ping=True, pool_size=5, max_overflow=0)
        manager = await PostgresRAGManager.create(_engine, VECTOR_TABLE_NAME, OLLAMA_HOST)

        pdf_path = "data/tachycardia_1.pdf"
        if os.path.exists(pdf_path):
            result = await manager.index_file(pdf_path)
            print(result)
            search_results = await manager.search("What is tachycardia?")
            print(f"Search found {len(search_results)} result(s).")
        else:
            print(f"File not found: {pdf_path}")

    asyncio.run(_main())
