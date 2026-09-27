"""
Hybrid Question Management System
Combines local JSON storage with external API sources for new questions
"""

import json
import logging
import random
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

import requests

logger = logging.getLogger(__name__)


class HybridQuestionService:
    """Service that combines local questions with external sources."""

    def __init__(self, json_file_path: str = None):
        self.json_file_path = json_file_path or "data/kenya_questions.json"
        self.local_questions = self._load_local_questions()
        self.external_sources = self._initialize_external_sources()

    def _load_local_questions(self) -> Dict[str, Any]:
        """Load questions from local JSON file."""
        try:
            file_path = Path(self.json_file_path)
            if file_path.exists():
                with open(file_path, "r", encoding="utf-8") as f:
                    return json.load(f)
            else:
                logger.warning(f"Local questions file not found: {self.json_file_path}")
                return {"questions": [], "categories": []}
        except Exception as e:
            logger.error(f"Error loading local questions: {str(e)}")
            return {"questions": [], "categories": []}

    def _save_local_questions(self) -> bool:
        """Save questions back to local JSON file."""
        try:
            file_path = Path(self.json_file_path)
            file_path.parent.mkdir(parents=True, exist_ok=True)

            # Update metadata
            self.local_questions["metadata"][
                "last_updated"
            ] = datetime.now(timezone.utc).isoformat()
            self.local_questions["metadata"]["total_questions"] = len(
                self.local_questions["questions"]
            )

            with open(file_path, "w", encoding="utf-8") as f:
                json.dump(self.local_questions, f, indent=2, ensure_ascii=False)
            return True
        except Exception as e:
            logger.error(f"Error saving local questions: {str(e)}")
            return False

    def _initialize_external_sources(self) -> Dict[str, Dict[str, Any]]:
        """Initialize external question sources."""
        return {
            "kenya_open_data": {
                "name": "Kenya Open Data",
                "url": "https://opendata.go.ke/api/action/package_list",
                "enabled": True,
                "description": "Generate questions from Kenya Open Data datasets",
            },
            "world_bank_kenya": {
                "name": "World Bank Kenya Data",
                "url": "https://api.worldbank.org/v2/country/KE/indicator",
                "enabled": True,
                "description": "Generate questions from World Bank data about Kenya",
            },
            "african_development_bank": {
                "name": "African Development Bank",
                "url": "https://www.afdb.org/en/knowledge/statistics",
                "enabled": False,
                "description": "Generate questions from AfDB statistics",
            },
        }

    def get_daily_questions(
        self,
        category: Optional[str] = None,
        difficulty_level: Optional[int] = None,
        limit: int = 10,
        mix_sources: bool = True,
    ) -> List[Dict[str, Any]]:
        """Get daily questions from local and external sources."""

        all_questions = []

        # Get local questions
        local_questions = self._get_local_questions(category, difficulty_level, limit)
        all_questions.extend(local_questions)

        # Get external questions if enabled
        if mix_sources and len(all_questions) < limit:
            external_limit = limit - len(all_questions)
            external_questions = self._get_external_questions(category, external_limit)
            all_questions.extend(external_questions)

        # Randomize and limit
        # nondeterminism-ok: which quiz questions to show; a selection of questions, not a figure
        random.shuffle(all_questions)
        return all_questions[:limit]

    def _get_local_questions(
        self,
        category: Optional[str] = None,
        difficulty_level: Optional[int] = None,
        limit: int = 10,
    ) -> List[Dict[str, Any]]:
        """Get questions from local JSON file."""

        questions = self.local_questions.get("questions", [])

        # Filter by category
        if category:
            questions = [q for q in questions if q.get("category") == category]

        # Filter by difficulty
        if difficulty_level:
            questions = [
                q for q in questions if q.get("difficulty_level") == difficulty_level
            ]

        # Filter active questions only
        questions = [q for q in questions if q.get("is_active", True)]

        # Randomize and limit
        # nondeterminism-ok: which quiz questions to show; a selection of questions, not a figure
        random.shuffle(questions)
        return questions[:limit]

    def _get_external_questions(
        self, category: Optional[str] = None, limit: int = 5
    ) -> List[Dict[str, Any]]:
        """Get questions from external sources."""

        external_questions = []

        # Try to fetch from Kenya Open Data
        if self.external_sources["kenya_open_data"]["enabled"]:
            try:
                kenya_questions = self._fetch_kenya_open_data_questions(
                    category, limit // 2
                )
                external_questions.extend(kenya_questions)
            except Exception as e:
                logger.error(f"Error fetching from Kenya Open Data: {str(e)}")

        # Try to fetch from World Bank
        if self.external_sources["world_bank_kenya"]["enabled"]:
            try:
                wb_questions = self._fetch_world_bank_questions(category, limit // 2)
                external_questions.extend(wb_questions)
            except Exception as e:
                logger.error(f"Error fetching from World Bank: {str(e)}")

        return external_questions[:limit]

    def _fetch_kenya_open_data_questions(
        self, category: Optional[str] = None, limit: int = 3
    ) -> List[Dict[str, Any]]:
        """Generate questions based on Kenya Open Data."""

        # Sample questions that would be generated from Kenya Open Data insights
        sample_questions = [
            {
                # nondeterminism-ok: a quiz question identifier, not a figure
                "id": f"ext_kod_{random.randint(1000, 9999)}",
                "question_text": "Which platform provides open access to Kenya's government data?",
                "option_a": "Kenya Data Portal",
                "option_b": "Kenya Open Data",
                "option_c": "Kenya Information Hub",
                "option_d": "Kenya Statistics Portal",
                "correct_answer": "B",
                "explanation": "Kenya Open Data (opendata.go.ke) is the official platform for accessing government datasets.",
                "category": category or "financial_transparency",
                "difficulty_level": 2,
                "tags": ["kenya", "open_data", "transparency", "datasets"],
                "source_url": "https://opendata.go.ke",
                "is_active": True,
                "source": "Kenya Open Data",
            },
            {
                # nondeterminism-ok: a quiz question identifier, not a figure
                "id": f"ext_kod_{random.randint(1000, 9999)}",
                "question_text": "What type of budget data is typically available on Kenya Open Data?",
                "option_a": "Only national budget summaries",
                "option_b": "County and national budget details",
                "option_c": "Only county budgets",
                "option_d": "No budget data is available",
                "correct_answer": "B",
                "explanation": "Kenya Open Data provides detailed budget information for both national and county governments.",
                "category": category or "budget_basics",
                "difficulty_level": 3,
                "tags": ["kenya", "budget_data", "counties", "national"],
                "source_url": "https://opendata.go.ke",
                "is_active": True,
                "source": "Kenya Open Data",
            },
        ]

        # nondeterminism-ok: which quiz questions to show; a selection of questions, not a figure
        return random.sample(sample_questions, min(limit, len(sample_questions)))

    def _fetch_world_bank_questions(
        self, category: Optional[str] = None, limit: int = 3
    ) -> List[Dict[str, Any]]:
        """Generate questions based on World Bank Kenya data."""

        sample_questions = [
            {
                # nondeterminism-ok: a quiz question identifier, not a figure
                "id": f"ext_wb_{random.randint(1000, 9999)}",
                "question_text": "According to World Bank data, what is Kenya's approximate GDP per capita category?",
                "option_a": "Low income",
                "option_b": "Lower middle income",
                "option_c": "Upper middle income",
                "option_d": "High income",
                "correct_answer": "B",
                "explanation": "Kenya is classified as a lower middle income country by World Bank standards.",
                "category": category or "public_finance",
                "difficulty_level": 3,
                "tags": ["kenya", "world_bank", "GDP", "classification"],
                "source_url": "https://data.worldbank.org/country/kenya",
                "is_active": True,
                "source": "World Bank Kenya Data",
            }
        ]

        # nondeterminism-ok: which quiz questions to show; a selection of questions, not a figure
        return random.sample(sample_questions, min(limit, len(sample_questions)))

    def add_question(self, question_data: Dict[str, Any]) -> Dict[str, Any]:
        """Add a new question to local storage."""

        # Generate new ID
        existing_ids = [
            q.get("id", 0) for q in self.local_questions.get("questions", [])
        ]
        max_id = max(existing_ids) if existing_ids else 0
        new_id = max_id + 1

        # Prepare question
        question_data["id"] = new_id
        question_data["created_at"] = datetime.now(timezone.utc).isoformat()
        question_data["is_active"] = question_data.get("is_active", True)

        # Add to local storage
        if "questions" not in self.local_questions:
            self.local_questions["questions"] = []

        self.local_questions["questions"].append(question_data)

        # Save to file
        if self._save_local_questions():
            return {
                "success": True,
                "message": "Question added successfully",
                "id": new_id,
            }
        else:
            return {"success": False, "message": "Failed to save question"}

    def update_question(
        self, question_id: int, update_data: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Update an existing question in local storage."""

        questions = self.local_questions.get("questions", [])

        for i, question in enumerate(questions):
            if question.get("id") == question_id:
                # Update fields
                for key, value in update_data.items():
                    question[key] = value
                question["updated_at"] = datetime.now(timezone.utc).isoformat()

                # Save to file
                if self._save_local_questions():
                    return {"success": True, "message": "Question updated successfully"}
                else:
                    return {"success": False, "message": "Failed to save updates"}

        return {"success": False, "message": "Question not found"}

    def delete_question(self, question_id: int) -> Dict[str, Any]:
        """Soft delete a question (mark as inactive)."""

        return self.update_question(question_id, {"is_active": False})

    def get_question_sources_status(self) -> Dict[str, Any]:
        """Get status of all question sources."""

        local_count = len(
            [
                q
                for q in self.local_questions.get("questions", [])
                if q.get("is_active", True)
            ]
        )

        return {
            "local_questions": {
                "count": local_count,
                "file_path": self.json_file_path,
                "last_updated": self.local_questions.get("metadata", {}).get(
                    "last_updated"
                ),
                "status": "operational",
            },
            "external_sources": {
                name: {
                    "enabled": config["enabled"],
                    "description": config["description"],
                    "status": "operational" if config["enabled"] else "disabled",
                }
                for name, config in self.external_sources.items()
            },
        }

    def refresh_from_external_sources(self) -> Dict[str, Any]:
        """Fetch new questions from external sources and add to local storage."""

        new_questions_count = 0
        errors = []

        # Fetch from each enabled external source
        for source_name, config in self.external_sources.items():
            if not config["enabled"]:
                continue

            try:
                if source_name == "kenya_open_data":
                    new_questions = self._fetch_kenya_open_data_questions(limit=5)
                elif source_name == "world_bank_kenya":
                    new_questions = self._fetch_world_bank_questions(limit=5)
                else:
                    continue

                # Add each new question
                for question in new_questions:
                    result = self.add_question(question)
                    if result.get("success"):
                        new_questions_count += 1
                    else:
                        errors.append(f"{source_name}: {result.get('message')}")

            except Exception as e:
                errors.append(f"{source_name}: {str(e)}")

        return {
            "success": len(errors) == 0,
            "new_questions_added": new_questions_count,
            "errors": errors,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
