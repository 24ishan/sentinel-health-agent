"""
Clinical prompts for RAG system.

Centralized location for all prompt templates used in the RAG service.
"""


class ClinicalPrompts:
    """Collection of clinical prompts used in RAG service."""

    # ── Original prompt (no patient context) ──────────────────────────────
    CLINICAL_ADVICE_TEMPLATE = """Context: {context}
Patient HR: {heart_rate}
Based ONLY on the context above, provide a 1-sentence medical instruction."""

    # ── Enriched prompt (with patient demographics + medical history) ──────
    CLINICAL_ADVICE_WITH_PATIENT_TEMPLATE = """You are a clinical AI assistant.

PATIENT INFORMATION:
  Name: {patient_name}
  Gender: {gender}
  Date of Birth: {dob}

MEDICAL HISTORY:
  Allergies: {allergies}
  Current Medications: {current_medications}
  Chronic Conditions: {chronic_conditions}
  Clinical Notes: {notes}

CLINICAL CONTEXT (from medical knowledge base):
{context}

CURRENT VITAL:
  Heart Rate: {heart_rate} BPM

Using the patient's profile, medical history, and the clinical context above,
provide a concise 1-2 sentence clinical recommendation for the nurse.
Flag any allergy or medication interactions if relevant."""

    CONTEXT_SUMMARIZATION = """Summarize the following clinical context in 1-2 sentences:
{context}"""

    RISK_ASSESSMENT = """Assess the clinical risk for a patient with heart rate {heart_rate} BPM.
Context: {context}
Provide severity assessment: LOW, MODERATE, HIGH, or CRITICAL."""

    # ── Static methods ─────────────────────────────────────────────────────

    @staticmethod
    def get_clinical_advice_prompt(context: str, heart_rate: int) -> str:
        """Format basic clinical advice prompt (no patient context)."""
        return ClinicalPrompts.CLINICAL_ADVICE_TEMPLATE.format(
            context=context, heart_rate=heart_rate
        )

    @staticmethod
    def get_enriched_advice_prompt(
        context: str,
        heart_rate: int,
        patient_name: str = "Unknown",
        gender: str = "Not specified",
        dob: str = "Unknown",
        allergies: str = "None known",
        current_medications: str = "None",
        chronic_conditions: str = "None",
        notes: str = "None",
    ) -> str:
        """
        Format an enriched clinical advice prompt that includes full
        patient demographics and medical history for context-aware LLM advice.

        Args:
            context: Clinical context retrieved from vector store
            heart_rate: Patient's current heart rate in BPM
            patient_name: Patient's full name
            gender: Patient's gender
            dob: Patient's date of birth
            ward: Hospital ward / unit
            allergies: Known allergies
            current_medications: Current medication list
            chronic_conditions: Known chronic conditions
            notes: Additional clinical notes

        Returns:
            str: Formatted enriched prompt for LLM
        """
        return ClinicalPrompts.CLINICAL_ADVICE_WITH_PATIENT_TEMPLATE.format(
            context=context,
            heart_rate=heart_rate,
            patient_name=patient_name,
            gender=gender,
            dob=dob,
            allergies=allergies,
            current_medications=current_medications,
            chronic_conditions=chronic_conditions,
            notes=notes,
        )

    @staticmethod
    def get_risk_assessment_prompt(context: str, heart_rate: int) -> str:
        """Format risk assessment prompt."""
        return ClinicalPrompts.RISK_ASSESSMENT.format(
            context=context, heart_rate=heart_rate
        )

    @staticmethod
    def get_context_summarization_prompt(context: str) -> str:
        """Format context summarization prompt."""
        return ClinicalPrompts.CONTEXT_SUMMARIZATION.format(context=context)

