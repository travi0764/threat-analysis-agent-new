"""
LangGraph agent for threat analysis.
Implements Plan → Act → Observe → Reason workflow for intelligent classification.
"""

import operator
from datetime import datetime
from typing import Annotated, Any, Dict, List, Optional, TypedDict

from langchain_core.messages import HumanMessage, SystemMessage
from langchain_core.output_parsers import JsonOutputParser
from langchain_openai import ChatOpenAI
from langgraph.graph import END, StateGraph
from pydantic import BaseModel, Field

from app.config import get_settings
from app.logging_config import get_logger
from app.storage.models import Indicator, RiskLevel

logger = get_logger(__name__)


# Pydantic models for structured outputs
class ClassificationOutput(BaseModel):
    """Structured output for classification."""

    risk_level: str = Field(description="Risk level: high, medium, or low")
    risk_score: float = Field(description="Risk score from 0.0 to 10.0")
    confidence: float = Field(
        description="Confidence in classification from 0.0 to 1.0"
    )
    reasoning: str = Field(description="Detailed reasoning for the classification")
    key_factors: List[str] = Field(
        description="Key factors that influenced the decision"
    )


class AgentState(TypedDict):
    """State of the threat analysis agent."""

    # Input
    indicator: Dict[str, Any]  # Indicator data
    enrichments: List[Dict[str, Any]]  # Enrichment data

    # Agent workflow
    plan: str  # Analysis plan
    observations: Annotated[List[str], operator.add]  # Observations from enrichments
    reasoning_steps: Annotated[List[str], operator.add]  # Reasoning steps

    # Output
    classification: Optional[Dict[str, Any]]  # Final classification
    error: Optional[str]  # Error message if any


class ThreatAnalysisAgent:
    """
    LangGraph-based agent for threat indicator analysis.
    Follows Plan → Act → Observe → Reason workflow.
    """

    def __init__(
        self, model_name: Optional[str] = None, temperature: Optional[float] = None
    ):
        """
        Initialize the threat analysis agent.

        Args:
            model_name: OpenAI model name (from config if None)
            temperature: Model temperature (from config if None)
        """
        settings = get_settings()

        self.model_name = model_name or settings.openai.model
        self.temperature = temperature or settings.openai.temperature

        # Initialize LLM
        self.llm = ChatOpenAI(
            model=self.model_name,
            temperature=self.temperature,
            api_key=settings.openai_api_key,
        )

        # Build the graph
        self.graph = self._build_graph()

        # Classification thresholds
        self.high_threshold = settings.classification.high_risk_threshold
        self.medium_threshold = settings.classification.medium_risk_threshold

        logger.info(
            f"Threat analysis agent initialized with model={self.model_name}, "
            f"thresholds: high={self.high_threshold}, medium={self.medium_threshold}"
        )

    def _build_graph(self) -> StateGraph:
        """Build the LangGraph workflow."""
        workflow = StateGraph(AgentState)

        # Add nodes
        workflow.add_node("plan", self._plan_node)
        workflow.add_node("observe", self._observe_node)
        workflow.add_node("reason", self._reason_node)

        # Define edges
        workflow.set_entry_point("plan")
        workflow.add_edge("plan", "observe")
        workflow.add_edge("observe", "reason")
        workflow.add_edge("reason", END)

        return workflow.compile()

    def _plan_node(self, state: AgentState) -> Dict[str, Any]:
        """
        Plan node: Analyze the indicator and enrichments to create an analysis plan.
        """
        indicator = state["indicator"]
        enrichments = state["enrichments"]

        logger.debug(f"Planning analysis for {indicator['type']}: {indicator['value']}")

        # Create plan based on available enrichments
        plan_parts = [
            f"Analyzing {indicator['type']} indicator: {indicator['value']}",
            f"Available enrichment data: {len(enrichments)} sources",
        ]

        enrichment_types = [e.get("enrichment_type") for e in enrichments]
        if enrichment_types:
            plan_parts.append(f"Enrichment types: {', '.join(enrichment_types)}")

        plan = " | ".join(plan_parts)

        return {"plan": plan}

    def _observe_node(self, state: AgentState) -> Dict[str, Any]:
        """
        Observe node: Extract key observations from enrichment data.
        """
        enrichments = state["enrichments"]
        observations = []

        logger.debug(f"Observing enrichment data ({len(enrichments)} sources)")

        for enrichment in enrichments:
            enrichment_type = enrichment.get("enrichment_type", "unknown")
            score = enrichment.get("score", 0)
            success = enrichment.get("success", False)

            if not success:
                observations.append(
                    f"{enrichment_type}: enrichment failed - {enrichment.get('error_message', 'unknown error')}"
                )
                continue

            data = enrichment.get("data", {})

            # Extract meaningful observations based on enrichment type
            if enrichment_type == "whois":
                obs = self._observe_whois(data, score)
                observations.extend(obs)
            elif enrichment_type == "ip_reputation":
                obs = self._observe_ip_reputation(data, score)
                observations.extend(obs)
            elif enrichment_type == "hash_lookup":
                obs = self._observe_hash_lookup(data, score)
                observations.extend(obs)
            else:
                observations.append(f"{enrichment_type}: score={score}")

        return {"observations": observations}

    def _observe_whois(self, data: Dict[str, Any], score: float) -> List[str]:
        """Extract observations from WHOIS data."""
        observations = []

        # Domain age
        creation_date = data.get("creation_date")
        if creation_date:
            try:
                created = datetime.fromisoformat(creation_date)
                age_days = (datetime.utcnow() - created).days

                if age_days < 30:
                    observations.append(
                        f"Domain is very new (created {age_days} days ago) - HIGH RISK"
                    )
                elif age_days < 90:
                    observations.append(
                        f"Domain is new (created {age_days} days ago) - MEDIUM RISK"
                    )
                elif age_days < 365:
                    observations.append(
                        f"Domain is recent (created {age_days} days ago)"
                    )
                else:
                    observations.append(f"Domain is {age_days} days old - established")
            except:
                pass

        # Registrar
        registrar = data.get("registrar")
        if registrar:
            observations.append(f"Registered with {registrar}")

        # Country
        country = data.get("registrant_country")
        if country:
            high_risk_countries = ["CN", "RU", "BR", "NG"]
            if country in high_risk_countries:
                observations.append(
                    f"Registered in {country} - potentially high-risk region"
                )
            else:
                observations.append(f"Registered in {country}")

        # DNSSEC
        if not data.get("dnssec"):
            observations.append("No DNSSEC - slightly elevated risk")

        observations.append(f"WHOIS risk score: {score}/10")

        return observations

    def _observe_ip_reputation(self, data: Dict[str, Any], score: float) -> List[str]:
        """Extract observations from IP reputation data."""
        observations = []

        # Abuse confidence
        abuse_score = data.get("abuse_confidence_score", 0)
        if abuse_score >= 80:
            observations.append(f"High abuse confidence ({abuse_score}%) - CRITICAL")
        elif abuse_score >= 50:
            observations.append(
                f"Moderate abuse confidence ({abuse_score}%) - HIGH RISK"
            )
        elif abuse_score >= 20:
            observations.append(f"Some abuse reports ({abuse_score}%)")
        else:
            observations.append(f"Low abuse confidence ({abuse_score}%)")

        # Total reports
        total_reports = data.get("total_reports", 0)
        if total_reports > 100:
            observations.append(f"Extensively reported ({total_reports} reports)")
        elif total_reports > 10:
            observations.append(f"Multiple abuse reports ({total_reports})")

        # Abuse categories
        categories = data.get("abuse_categories", [])
        if categories:
            observations.append(f"Abuse types: {', '.join(categories)}")

        # Tor/Proxy
        if data.get("is_tor"):
            observations.append("Tor exit node detected - anonymization risk")
        if data.get("is_proxy"):
            observations.append("Proxy detected - potential hiding")

        # ISP and usage
        isp = data.get("isp")
        usage_type = data.get("usage_type")
        if isp and usage_type:
            observations.append(f"Hosted on {isp} ({usage_type})")

        observations.append(f"IP reputation score: {score}/10")

        return observations

    def _observe_hash_lookup(self, data: Dict[str, Any], score: float) -> List[str]:
        """Extract observations from hash lookup data."""
        observations = []

        # Detection ratio
        detection_ratio = data.get("detection_ratio", "0/0")
        detections = data.get("detections", 0)
        total = data.get("total_engines", 70)

        if detections > 0:
            percentage = (detections / total) * 100 if total > 0 else 0

            if percentage >= 50:
                observations.append(
                    f"HIGH malware detection ({detection_ratio}) - CRITICAL"
                )
            elif percentage >= 20:
                observations.append(
                    f"MODERATE malware detection ({detection_ratio}) - HIGH RISK"
                )
            else:
                observations.append(f"LOW malware detection ({detection_ratio})")
        else:
            observations.append("No malware detections - appears clean")

        # Malware families
        families = data.get("malware_families", [])
        if families:
            observations.append(f"Identified malware families: {', '.join(families)}")

        # File type
        file_type = data.get("file_type")
        if file_type:
            observations.append(f"File type: {file_type}")

        # Is malware
        if data.get("is_malware"):
            observations.append("CONFIRMED MALWARE")

        observations.append(f"Hash lookup score: {score}/10")

        return observations

    def _reason_node(self, state: AgentState) -> Dict[str, Any]:
        """
        Reason node: Use LLM to analyze observations and produce classification.
        """
        indicator = state["indicator"]
        observations = state["observations"]
        enrichments = state["enrichments"]

        logger.debug(f"Reasoning about {indicator['type']}: {indicator['value']}")

        # Calculate aggregate score from enrichments
        scores = [e.get("score", 0) for e in enrichments if e.get("success")]
        avg_score = sum(scores) / len(scores) if scores else 0
        max_score = max(scores) if scores else 0
        # Always anchor the final risk score to the strongest signal from any enricher
        final_score = max_score if scores else 0.0

        # Build prompt for LLM
        system_prompt = self._build_system_prompt()
        user_prompt = self._build_user_prompt(
            indicator, observations, avg_score, max_score
        )

        try:
            # Call LLM with structured output
            parser = JsonOutputParser(pydantic_object=ClassificationOutput)

            messages = [
                SystemMessage(content=system_prompt),
                HumanMessage(
                    content=user_prompt + "\n\n" + parser.get_format_instructions()
                ),
            ]

            response = self.llm.invoke(messages)
            classification_data = parser.parse(response.content)

            # Convert to dict and add metadata (Pydantic v2 uses model_dump)
            # classification = classification_data.model_dump() if hasattr(classification_data, 'model_dump') else classification_data.dict()
            classification = (
                classification_data
                if isinstance(classification_data, dict)
                else (
                    classification_data.model_dump()
                    if hasattr(classification_data, "model_dump")
                    else classification_data.dict()
                )
            )
            classification["model"] = self.model_name
            classification["enrichment_score_avg"] = avg_score
            classification["enrichment_score_max"] = max_score
            classification["classified_at"] = datetime.utcnow().isoformat()

            # Align the delivered risk score and level with the strongest enrichment evidence.
            if scores:
                clamped_final_score = max(0.0, min(10.0, final_score))
                classification["risk_score"] = clamped_final_score

                # Reconcile risk level with configured thresholds so UI stays consistent
                if clamped_final_score >= self.high_threshold:
                    classification["risk_level"] = RiskLevel.HIGH.value
                elif clamped_final_score >= self.medium_threshold:
                    classification["risk_level"] = RiskLevel.MEDIUM.value
                else:
                    classification["risk_level"] = RiskLevel.LOW.value
            else:
                classification["risk_score"] = max(
                    0.0, min(10.0, classification.get("risk_score", 0.0))
                )

            logger.info(
                f"Classification complete: {indicator['value']} -> "
                f"{classification['risk_level']} (score={classification['risk_score']}, "
                f"confidence={classification['confidence']})"
            )

            return {"classification": classification}

        except Exception as e:
            logger.error(f"Classification failed: {e}")
            return {"error": str(e)}

    def _build_system_prompt(self) -> str:
        """Build the system prompt for the LLM."""
        return """You are an expert cybersecurity analyst specializing in threat intelligence analysis.

Your task is to classify threat indicators based on enrichment data and observations.

Risk Classification Guidelines:
- HIGH RISK (score 7.0-10.0): Clear indicators of malicious activity, active threats, confirmed malware
- MEDIUM RISK (score 4.0-6.9): Suspicious patterns, potential threats, requires monitoring
- LOW RISK (score 0.0-3.9): Minimal indicators, likely benign, low threat level

Consider these factors in your analysis:
1. Enrichment scores from technical sources
2. Specific observations about the indicator
3. Patterns that indicate malicious intent
4. Context of the indicator type (domain, IP, hash)
5. Confidence in the available data

Provide:
1. A clear risk level classification
2. A precise risk score (0.0 to 10.0)
3. Your confidence level (0.0 to 1.0)
4. Detailed reasoning explaining your decision
5. Key factors that influenced your classification

Be analytical, precise, and security-focused in your assessment."""

    def _build_user_prompt(
        self,
        indicator: Dict[str, Any],
        observations: List[str],
        avg_score: float,
        max_score: float,
    ) -> str:
        """Build the user prompt with indicator data."""
        obs_text = "\n".join(f"- {obs}" for obs in observations)

        return f"""Analyze this threat indicator:

Indicator Type: {indicator["type"]}
Indicator Value: {indicator["value"]}
Source: {indicator.get("source_name", "unknown")}
Tags: {", ".join(indicator.get("tags", []))}

Enrichment Analysis:
Average Enrichment Score: {avg_score:.2f}/10.0
Maximum Enrichment Score: {max_score:.2f}/10.0
Risk Assessment Guidance: Treat the highest enrichment score as the primary risk baseline to avoid diluting strong signals.

Key Observations:
{obs_text if obs_text else "- No observations available"}

Based on this information, provide a comprehensive threat classification."""

    async def classify_indicator(
        self, indicator: Indicator, enrichments: List[Dict[str, Any]]
    ) -> Dict[str, Any]:
        """
        Classify a threat indicator using the agent workflow.

        Args:
            indicator: Indicator to classify
            enrichments: List of enrichment data

        Returns:
            Classification result dictionary
        """
        # Prepare state
        initial_state = {
            "indicator": {
                "id": indicator.id,
                "type": indicator.indicator_type.value,
                "value": indicator.value,
                "source_type": indicator.source_type.value,
                "source_name": indicator.source_name,
                "tags": indicator.tags or [],
            },
            "enrichments": enrichments,
            "observations": [],
            "reasoning_steps": [],
            "classification": None,
            "error": None,
        }

        # Run the graph
        try:
            result = await self.graph.ainvoke(initial_state)

            if result.get("error"):
                logger.error(f"Agent classification failed: {result['error']}")
                return None

            return result.get("classification")

        except Exception as e:
            logger.error(f"Agent execution failed: {e}")
            return None
