"""
Medical RAG Service - Production Ready Version

This module implements a Retrieval-Augmented Generation (RAG) system
for generating clinical advice based on patient vitals (heart rate).
"""

import asyncio
import time
from datetime import datetime
from typing import Optional

from langchain_ollama import OllamaEmbeddings, OllamaLLM
from langchain_postgres import PGVectorStore, PGEngine

from utils.config import (
    DATABASE_URL,
    VECTOR_TABLE_NAME,
    MEDICAL_EMBEDDING_MODEL,
    LLM_MODEL,
)
from app import setup_logging
from app.backend.services.prompts import ClinicalPrompts
from app.utils.retry import async_retry, RetryConfig

logger = setup_logging()

# Configuration constants
MIN_VALID_HEART_RATE = 30  # BPM
MAX_VALID_HEART_RATE = 200  # BPM
CONTEXT_MAX_LENGTH = 2000  # characters
VECTOR_SEARCH_K = 2  # number of documents to retrieve

# Retry configuration for Ollama calls
OLLAMA_RETRY_CONFIG = RetryConfig(
    max_attempts=3,
    base_delay=1.0,
    exponential_base=2.0,
    max_delay=30.0,
    jitter=True,
    retriable_exceptions=(ConnectionError, TimeoutError, OSError, RuntimeError)
)


class MedicalRAG:
    """
    Medical RAG (Retrieval-Augmented Generation) Service.

    Retrieves clinical context from vector store and generates
    medical advice using Ollama LLM based on patient vitals.

    Attributes:
        embeddings (OllamaEmbeddings): Embeddings model for similarity search
        llm (OllamaLLM): Language model for generating advice
        vector_store (Optional[PGVectorStore]): PostgreSQL vector store
        engine (Optional[PGEngine]): Database engine with connection pooling
        is_initialized (bool): Service initialization status
    """

    def __init__(self) -> None:
        """Initialize MedicalRAG instance with connection pooling."""
        self.embeddings: OllamaEmbeddings = OllamaEmbeddings(
            model=MEDICAL_EMBEDDING_MODEL
        )
        self.db_url: str = DATABASE_URL
        self.vector_store: Optional[PGVectorStore] = None
        self.llm: OllamaLLM = OllamaLLM(model=LLM_MODEL)

        # Initialize engine once for connection pooling
        self.engine: Optional[PGEngine] = PGEngine.from_connection_string(self.db_url)
        self.is_initialized: bool = False

    async def initialize(self) -> None:
        """
        Initialize vector store during startup.

        Raises:
            RuntimeError: If initialization fails
        """
        if self.is_initialized:
            logger.debug("RAG service already initialized")
            return

        try:
            logger.info("Initializing RAG vector store...")
            self.vector_store = await PGVectorStore.create(
                engine=self.engine,
                table_name=VECTOR_TABLE_NAME,
                embedding_service=self.embeddings,
                id_column="langchain_id",
                content_column="content",
            )
            self.is_initialized = True
            logger.info("✅ RAG vector store initialized successfully")
        except Exception as e:
            logger.error(f"Failed to initialize vector store: {e}", exc_info=True)
            raise RuntimeError("Vector store initialization failed") from e

    async def _get_store(self) -> PGVectorStore:
        """
        Get the initialized vector store.

        Returns:
            PGVectorStore: The vector store instance

        Raises:
            RuntimeError: If not initialized
        """
        if self.vector_store is None:
            raise RuntimeError(
                "Vector store not initialized. Call initialize() first."
            )
        return self.vector_store

    @async_retry(OLLAMA_RETRY_CONFIG)
    async def _call_ollama_embeddings(self, query: str) -> list[float]:
        """Call Ollama embeddings with retry logic."""
        return self.embeddings.embed_query(query)

    @async_retry(OLLAMA_RETRY_CONFIG)
    async def _call_ollama_llm(self, prompt: str) -> str:
        """Call Ollama LLM with retry logic."""
        return await self.llm.ainvoke(prompt)

    def _validate_heart_rate(self, heart_rate: int) -> None:
        """
        Validate heart rate input.

        Args:
            heart_rate: Heart rate to validate

        Raises:
            ValueError: If invalid
        """
        if not isinstance(heart_rate, (int, float)):
            raise ValueError(
                f"heart_rate must be numeric, got {type(heart_rate).__name__}"
            )

        if heart_rate <= 0:
            raise ValueError(f"heart_rate must be positive, got {heart_rate}")

        if heart_rate < MIN_VALID_HEART_RATE or heart_rate > MAX_VALID_HEART_RATE:
            logger.warning(
                f"Heart rate {heart_rate} BPM outside normal range "
                f"({MIN_VALID_HEART_RATE}-{MAX_VALID_HEART_RATE})"
            )

    async def get_clinical_advice(self, heart_rate: int) -> str:
        """
        Generate clinical advice based on patient heart rate.

        Args:
            heart_rate: Patient's heart rate in BPM (30-200)

        Returns:
            str: Clinical advice (1-sentence recommendation)

        Raises:
            ValueError: If heart_rate invalid
            RuntimeError: If vector store not initialized
            ConnectionError: If cannot connect to Ollama
            TimeoutError: If Ollama timeout
        """
        try:
            # Validate input
            self._validate_heart_rate(heart_rate)

            # Get vector store
            store = await self._get_store()

            # Search for relevant clinical documents
            query = f"Clinical guidelines for heart rate of {heart_rate} BPM"
            docs = await store.asimilarity_search(query, k=VECTOR_SEARCH_K)

            if not docs:
                logger.warning(f"No documents found for HR {heart_rate} BPM")
                return "No clinical guidelines found for this heart rate."

            # Prepare context
            context = "\n".join([doc.page_content for doc in docs])

            if len(context) > CONTEXT_MAX_LENGTH:
                context = context[:CONTEXT_MAX_LENGTH] + "..."
                logger.warning(
                    f"Context truncated to {CONTEXT_MAX_LENGTH} characters"
                )

            logger.debug(
                f"Retrieved {len(docs)} documents, "
                f"context length: {len(context)} characters"
            )

            # Get clinical advice
            full_prompt = ClinicalPrompts.get_clinical_advice_prompt(
                context, heart_rate
            )
            response = await self._call_ollama_llm(full_prompt)

            logger.info(f"✅ Retrieved clinical advice for HR {heart_rate} BPM")
            return response

        except ValueError as e:
            logger.error(f"Input validation error: {e}")
            raise
        except Exception as e:
            logger.error(
                f"Failed to get clinical advice for HR {heart_rate}: {e}",
                exc_info=True,
            )
            raise

    async def health_check(self) -> dict:
        """
        Perform comprehensive health check.

        Returns:
            dict: Health status with component statuses
        """
        errors: list[str] = []
        results = {}

        try:
            # Test embeddings
            start_time = time.time()
            try:
                test_embedding = await asyncio.to_thread(
                    self.embeddings.embed_query, "test"
                )
                results["embedding_model"] = len(test_embedding) > 0
                logger.debug(
                    f"✅ Embeddings OK ({time.time() - start_time:.2f}s)"
                )
            except Exception as e:
                results["embedding_model"] = False
                errors.append(f"Embeddings: {str(e)}")
                logger.error(f"❌ Embeddings failed: {e}")

            # Test vector store
            start_time = time.time()
            try:
                if not self.is_initialized:
                    await self.initialize()
                store = await self._get_store()
                results["vector_store"] = store is not None
                logger.debug(
                    f"✅ Vector store OK ({time.time() - start_time:.2f}s)"
                )
            except Exception as e:
                results["vector_store"] = False
                errors.append(f"Vector store: {str(e)}")
                logger.error(f"❌ Vector store failed: {e}")

            # Test LLM
            start_time = time.time()
            try:
                response = await asyncio.wait_for(
                    self._call_ollama_llm("Hello"), timeout=10.0
                )
                results["llm_model"] = bool(response)
                logger.debug(f"✅ LLM OK ({time.time() - start_time:.2f}s)")
            except asyncio.TimeoutError:
                results["llm_model"] = False
                errors.append("LLM: Timeout")
                logger.error("❌ LLM timeout")
            except Exception as e:
                results["llm_model"] = False
                errors.append(f"LLM: {str(e)}")
                logger.error(f"❌ LLM failed: {e}")

            # Determine status
            all_ok = all(results.values())
            status = (
                "healthy"
                if all_ok
                else ("degraded" if any(results.values()) else "unhealthy")
            )

            health_report = {
                "status": status,
                **results,
                "timestamp": datetime.now().isoformat(),
                "errors": errors if errors else None,
            }

            logger.info(f"Health check: {status}")
            return health_report

        except Exception as e:
            logger.error(f"Health check failed: {e}", exc_info=True)
            return {
                "status": "unhealthy",
                "error": str(e),
                "timestamp": datetime.now().isoformat(),
            }

    async def close(self) -> None:
        """Cleanup resources on shutdown."""
        if self.engine:
            await self.engine.dispose()
            logger.info("✅ RAG service engine disposed")
