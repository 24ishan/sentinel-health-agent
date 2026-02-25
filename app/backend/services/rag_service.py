import os
from dotenv import load_dotenv
from langchain_ollama import OllamaEmbeddings
from langchain_postgres import PGVectorStore
from langchain_postgres import PGEngine
from langchain_ollama import OllamaLLM

load_dotenv()
MEDICAL_EMBEDDING = os.getenv("MEDICAL_EMBEDDING")

class MedicalRAG:
    def __init__(self):
        self.embeddings = OllamaEmbeddings(model="llama3")
        self.db_url = os.getenv("DATABASE_URL")
        self.vector_store = None
        self.llm = OllamaLLM(model="llama3")

    async def _get_store(self):
        """Initializes the vector store asynchronously if it doesn't exist."""
        if self.vector_store is None:
            # Create an async engine
            engine = PGEngine.from_connection_string(self.db_url)

            # Initialize the store
            self.vector_store = await PGVectorStore.create(
                engine=engine,
                table_name=MEDICAL_EMBEDDING,
                embedding_service=self.embeddings,
                id_column="id",
                content_column="document"
            )
        return self.vector_store

    async def get_clinical_advice(self, heart_rate: int):
        try:
            store = await self._get_store()
            query = f"Clinical guidelines for heart rate of {heart_rate} BPM"
            docs = await store.asimilarity_search(query, k=2)

            context = "\n".join([doc.page_content for doc in docs])
            print("context:::::::::::::",context)
            full_prompt = f"""
            Context: {context}
            Patient HR: {heart_rate}
            Based ONLY on the context above, provide a 1-sentence medical instruction.
            """
            response = await self.llm.ainvoke(full_prompt)
            return response

        except Exception as e:
            return f"Error: {e}"

rag_agent = MedicalRAG()
