"""
Clinical prompts for RAG system.

Centralized location for all prompt templates used in the RAG service.
This makes it easy to update prompts without modifying the main service logic.
"""


class ClinicalPrompts:
    """Collection of clinical prompts used in RAG service."""

    CLINICAL_ADVICE_TEMPLATE = """Context: {context}
Patient HR: {heart_rate}
Based ONLY on the context above, provide a 1-sentence medical instruction."""

    CONTEXT_SUMMARIZATION = """Summarize the following clinical context in 1-2 sentences:
{context}"""

    RISK_ASSESSMENT = """Assess the clinical risk for a patient with heart rate {heart_rate} BPM.
Context: {context}
Provide severity assessment: LOW, MODERATE, HIGH, or CRITICAL."""

    @staticmethod
    def get_clinical_advice_prompt(context: str, heart_rate: int) -> str:
        """
        Format clinical advice prompt.

        Args:
            context: Clinical context from vector store
            heart_rate: Patient's heart rate in BPM

        Returns:
            str: Formatted prompt for LLM
        """
        return ClinicalPrompts.CLINICAL_ADVICE_TEMPLATE.format(
            context=context, heart_rate=heart_rate
        )

    @staticmethod
    def get_risk_assessment_prompt(context: str, heart_rate: int) -> str:
        """
        Format risk assessment prompt.

        Args:
            context: Clinical context from vector store
            heart_rate: Patient's heart rate in BPM

        Returns:
            str: Formatted prompt for LLM
        """
        return ClinicalPrompts.RISK_ASSESSMENT.format(
            context=context, heart_rate=heart_rate
        )

    @staticmethod
    def get_context_summarization_prompt(context: str) -> str:
        """
        Format context summarization prompt.

        Args:
            context: Clinical context to summarize

        Returns:
            str: Formatted prompt for LLM
        """
        return ClinicalPrompts.CONTEXT_SUMMARIZATION.format(context=context)

