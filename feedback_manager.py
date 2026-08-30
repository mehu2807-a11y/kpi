"""
Feedback Manager - Captures and utilizes analyst/business-user feedback
to improve detection accuracy, action relevance, and narrative quality.
"""

from __future__ import annotations

from typing import List, Dict, Optional, Any
from dataclasses import dataclass, field
from enum import Enum
import json
import time
from datetime import datetime


class FeedbackType(Enum):
    ACTION_RELEVANCE = "action_relevance"      # Was the recommended action helpful?
    NARRATIVE_CLARITY = "narrative_clarity"    # Was the explanation clear?
    DETECTION_ACCURACY = "detection_accuracy"  # Was the anomaly detection correct?
    HYPOTHESIS_VALIDITY = "hypothesis_validity" # Was the identified root cause correct?
    PERSONA_APPROPRIATENESS = "persona_appropriateness" # Was the narrative right for the audience?


class FeedbackValue(Enum):
    EXCELLENT = 5
    GOOD = 4
    NEUTRAL = 3
    POOR = 2
    VERY_POOR = 1


@dataclass
class FeedbackRecord:
    """A single piece of feedback from an analyst or business user."""
    feedback_id: str
    timestamp: str
    feedback_type: FeedbackType
    value: FeedbackValue
    comments: Optional[str] = None
    # Context about what the feedback is referring to
    anomaly_id: Optional[str] = None
    persona: Optional[str] = None  # For narrative feedback
    hypothesis_index: Optional[int] = None  # For hypothesis feedback
    action_index: Optional[int] = None  # For action feedback
    # Who provided the feedback
    provider_role: str = "analyst"  # analyst, business_user, executive, etc.
    provider_id: str = "anonymous"


@dataclass
class FeedbackSummary:
    """Summary of feedback for a specific context."""
    feedback_type: FeedbackType
    total_count: int
    average_score: float
    recent_trend: str  # "improving", "declining", "stable"
    breakdown: Dict[FeedbackValue, int] = field(default_factory=dict)


class FeedbackManager:
    """Manages collection and analysis of feedback."""

    def __init__(self):
        self.feedback_records: List[FeedbackRecord] = []
        self._saved_count = 0
        # In a production system, this would be stored in a database

    def add_feedback(
        self,
        feedback_type: FeedbackType,
        value: FeedbackValue,
        comments: Optional[str] = None,
        anomaly_id: Optional[str] = None,
        persona: Optional[str] = None,
        hypothesis_index: Optional[int] = None,
        action_index: Optional[int] = None,
        provider_role: str = "analyst",
        provider_id: str = "anonymous"
    ) -> FeedbackRecord:
        """Add a new feedback record."""
        feedback_id = f"fb_{int(time.time() * 1000)}_{len(self.feedback_records)}"

        record = FeedbackRecord(
            feedback_id=feedback_id,
            timestamp=datetime.now().isoformat(),
            feedback_type=feedback_type,
            value=value,
            comments=comments,
            anomaly_id=anomaly_id,
            persona=persona,
            hypothesis_index=hypothesis_index,
            action_index=action_index,
            provider_role=provider_role,
            provider_id=provider_id
        )

        self.feedback_records.append(record)
        try:
            self.save_to_disk()
        except Exception:
            pass  # never let a disk write failure break the feedback submission
        return record

    def get_feedback_summary(
        self,
        feedback_type: Optional[FeedbackType] = None,
        anomaly_id: Optional[str] = None,
        days_back: int = 30
    ) -> FeedbackSummary:
        """Get summary of feedback matching criteria."""
        # Filter records
        filtered_records = self.feedback_records

        if feedback_type:
            filtered_records = [r for r in filtered_records if r.feedback_type == feedback_type]

        if anomaly_id:
            filtered_records = [r for r in filtered_records if r.anomaly_id == anomaly_id]

        # Filter by time (simplified - in production would use proper date filtering)
        # For now, we'll just use all records

        if not filtered_records:
            return FeedbackSummary(
                feedback_type=feedback_type or FeedbackType.ACTION_RELEVANCE,
                total_count=0,
                average_score=0.0,
                recent_trend="no_data"
            )

        # Calculate average score
        total_score = sum(r.value.value for r in filtered_records)
        average_score = total_score / len(filtered_records)

        # Calculate breakdown
        breakdown = {}
        for fb in FeedbackValue:
            breakdown[fb] = sum(1 for r in filtered_records if r.value == fb)

        # Determine trend (simplified)
        recent_trend = "stable"  # In production, would compare recent vs older
        if len(filtered_records) >= 10:
            recent_avg = sum(r.value.value for r in filtered_records[-5:]) / 5
            older_avg = sum(r.value.value for r in filtered_records[-10:-5]) / 5
            if recent_avg > older_avg + 0.5:
                recent_trend = "improving"
            elif recent_avg < older_avg - 0.5:
                recent_trend = "declining"

        return FeedbackSummary(
            feedback_type=feedback_type or FeedbackType.ACTION_RELEVANCE,
            total_count=len(filtered_records),
            average_score=average_score,
            recent_trend=recent_trend,
            breakdown=breakdown
        )

    def get_actionability_insights(self) -> List[str]:
        """Generate insights for improving the system based on feedback."""
        insights = []

        # Check action relevance
        action_fb = self.get_feedback_summary(FeedbackType.ACTION_RELEVANCE)
        if action_fb.average_score < 3.0:
            insights.append("Action recommendations need improvement - consider more specific, business-contextual actions")

        # Check narrative clarity
        narrative_fb = self.get_feedback_summary(FeedbackType.NARRATIVE_CLARITY)
        if narrative_fb.average_score < 3.0:
            insights.append("Narratives could be clearer - consider simplifying language and focusing on key insights")

        # Check detection accuracy
        detection_fb = self.get_feedback_summary(FeedbackType.DETECTION_ACCURACY)
        if detection_fb.average_score < 3.0:
            insights.append("Anomaly detection may need tuning - review false positive/negative rates")

        # Check hypothesis validity
        hypothesis_fb = self.get_feedback_summary(FeedbackType.HYPOTHESIS_VALIDITY)
        if hypothesis_fb.average_score < 3.0:
            insights.append("Root cause identification needs improvement - consider additional validation steps")

        return insights

    def save_to_disk(self, path: str = 'feedback_log.jsonl') -> None:
        """
        Appends all NEW (unsaved) feedback records to a JSONL file.
        Uses an append-only pattern — never rewrites the full file.
        
        Tracks which records have been saved via self._saved_count (added in __init__).
        Records added after the last save() call are the 'new' ones.
        """
        new_records = self.feedback_records[self._saved_count:]
        if not new_records:
            return
            
        with open(path, 'a') as f:
            for r in new_records:
                record_dict = {
                    "feedback_id": r.feedback_id,
                    "timestamp": r.timestamp,
                    "feedback_type": r.feedback_type.value,
                    "value": r.value.value,
                    "comments": r.comments,
                    "anomaly_id": r.anomaly_id,
                    "persona": r.persona,
                    "hypothesis_index": r.hypothesis_index,
                    "action_index": r.action_index,
                    "provider_role": r.provider_role,
                    "provider_id": r.provider_id
                }
                f.write(json.dumps(record_dict) + '\n')
        self._saved_count = len(self.feedback_records)

    @classmethod
    def load_from_disk(cls, path: str = 'feedback_log.jsonl') -> 'FeedbackManager':
        """
        Loads feedback records from a JSONL file into a new FeedbackManager.
        Each line is a JSON object (one record). Returns new FeedbackManager instance.
        Returns empty FeedbackManager if file doesn't exist.
        """
        import os
        instance = cls()
        if not os.path.exists(path):
            return instance
            
        try:
            with open(path, 'r') as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    item = json.loads(line)
                    record = FeedbackRecord(
                        feedback_id=item["feedback_id"],
                        timestamp=item["timestamp"],
                        feedback_type=FeedbackType(item["feedback_type"]),
                        value=FeedbackValue(item["value"]),
                        comments=item.get("comments"),
                        anomaly_id=item.get("anomaly_id"),
                        persona=item.get("persona"),
                        hypothesis_index=item.get("hypothesis_index"),
                        action_index=item.get("action_index"),
                        provider_role=item.get("provider_role", "analyst"),
                        provider_id=item.get("provider_id", "anonymous")
                    )
                    instance.feedback_records.append(record)
            instance._saved_count = len(instance.feedback_records)
        except Exception:
            pass
        return instance

    def get_recent_history(self, n: int = 50) -> list[dict]:
        """
        Returns the last n feedback records as plain dicts (JSON-serializable).
        Used by the /feedback/history endpoint.
        """
        recent = self.feedback_records[-n:] if n > 0 else self.feedback_records
        return [
            {
                "feedback_id": r.feedback_id,
                "timestamp": r.timestamp,
                "feedback_type": r.feedback_type.value,
                "value": r.value.value,
                "comments": r.comments,
                "anomaly_id": r.anomaly_id,
                "persona": r.persona,
                "hypothesis_index": r.hypothesis_index,
                "action_index": r.action_index,
                "provider_role": r.provider_role,
                "provider_id": r.provider_id
            }
            for r in recent
        ]

    def to_json(self) -> str:
        """Export feedback records as JSON."""
        return json.dumps([
            {
                "feedback_id": r.feedback_id,
                "timestamp": r.timestamp,
                "feedback_type": r.feedback_type.value,
                "value": r.value.value,
                "comments": r.comments,
                "anomaly_id": r.anomaly_id,
                "persona": r.persona,
                "hypothesis_index": r.hypothesis_index,
                "action_index": r.action_index,
                "provider_role": r.provider_role,
                "provider_id": r.provider_id
            }
            for r in self.feedback_records
        ], indent=2)

    @classmethod
    def from_json(cls, json_str: str) -> 'FeedbackManager':
        """Load feedback records from JSON."""
        instance = cls()
        data = json.loads(json_str)
        for item in data:
            record = FeedbackRecord(
                feedback_id=item["feedback_id"],
                timestamp=item["timestamp"],
                feedback_type=FeedbackType(item["feedback_type"]),
                value=FeedbackValue(item["value"]),
                comments=item.get("comments"),
                anomaly_id=item.get("anomaly_id"),
                persona=item.get("persona"),
                hypothesis_index=item.get("hypothesis_index"),
                action_index=item.get("action_index"),
                provider_role=item.get("provider_role", "analyst"),
                provider_id=item.get("provider_id", "anonymous")
            )
            instance.feedback_records.append(record)
        return instance


# Global feedback manager instance
FEEDBACK_MANAGER = FeedbackManager()

# Load persisted feedback from disk on module import
import os as _os
_FEEDBACK_LOG_PATH = _os.path.join(_os.path.dirname(__file__), 'feedback_log.jsonl')
if _os.path.exists(_FEEDBACK_LOG_PATH):
    try:
        _loaded = FeedbackManager.load_from_disk(_FEEDBACK_LOG_PATH)
        FEEDBACK_MANAGER.feedback_records = _loaded.feedback_records
        FEEDBACK_MANAGER._saved_count = len(FEEDBACK_MANAGER.feedback_records)
    except Exception:
        pass  # corrupted log — start fresh, don't crash