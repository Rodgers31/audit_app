"""
Learning Hub Question Management Service
Handles CRUD operations for quick questions and user answers
"""

import logging
import random
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

from database import get_db
from models import QuestionCategory, QuickQuestion, User, UserQuestionAnswer
from sqlalchemy import and_, func, or_
from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)


class QuestionService:
    """Service for managing learning hub questions."""

    def __init__(self, db: Session):
        self.db = db

    def get_daily_questions(
        self,
        user_id: Optional[int] = None,
        limit: int = 5,
        category: Optional[str] = None,
        difficulty_level: Optional[int] = None,
    ) -> List[QuickQuestion]:
        """Get daily questions for a user, avoiding recently answered ones."""

        query = self.db.query(QuickQuestion).filter(QuickQuestion.is_active == True)

        # Filter by category if specified
        if category:
            try:
                category_enum = QuestionCategory(category)
                query = query.filter(QuickQuestion.category == category_enum)
            except ValueError:
                logger.warning(f"Invalid category: {category}")

        # Filter by difficulty if specified
        if difficulty_level:
            query = query.filter(QuickQuestion.difficulty_level == difficulty_level)

        # Exclude questions answered by user in the last 3 days (if user_id provided)
        if user_id:
            recent_cutoff = datetime.now(timezone.utc) - timedelta(days=3)
            answered_question_ids = (
                self.db.query(UserQuestionAnswer.question_id)
                .filter(
                    and_(
                        UserQuestionAnswer.user_id == user_id,
                        UserQuestionAnswer.answered_at >= recent_cutoff,
                    )
                )
                .subquery()
            )

            query = query.filter(~QuickQuestion.id.in_(answered_question_ids))

        # Get all matching questions
        all_questions = query.all()

        # Randomize and limit
        if len(all_questions) > limit:
            # nondeterminism-ok: which quiz questions to show; a selection of questions, not a figure
            return random.sample(all_questions, limit)
        else:
            return all_questions

    def submit_answer(
        self, user_id: int, question_id: int, selected_answer: str
    ) -> Dict[str, Any]:
        """Submit an answer and return the result."""

        # Get the question
        question = (
            self.db.query(QuickQuestion).filter(QuickQuestion.id == question_id).first()
        )

        if not question:
            raise ValueError(f"Question {question_id} not found")

        # Check if correct
        is_correct = selected_answer.upper() == question.correct_answer.upper()

        # Save the answer
        user_answer = UserQuestionAnswer(
            user_id=user_id,
            question_id=question_id,
            selected_answer=selected_answer.upper(),
            is_correct=is_correct,
            answered_at=datetime.now(timezone.utc),
        )

        self.db.add(user_answer)
        self.db.commit()

        # Calculate points
        points_earned = 0
        if is_correct:
            base_points = 10
            difficulty_multiplier = question.difficulty_level
            points_earned = base_points * difficulty_multiplier

        return {
            "question_id": question_id,
            "selected_answer": selected_answer.upper(),
            "correct_answer": question.correct_answer,
            "is_correct": is_correct,
            "explanation": question.explanation or "",
            "points_earned": points_earned,
        }

    def get_user_stats(self, user_id: int) -> Dict[str, Any]:
        """Get learning statistics for a user."""

        today = datetime.now(timezone.utc).date()
        week_ago = datetime.now(timezone.utc) - timedelta(days=7)

        # Total questions answered
        total_answered = (
            self.db.query(UserQuestionAnswer)
            .filter(UserQuestionAnswer.user_id == user_id)
            .count()
        )

        # Questions answered today
        answered_today = (
            self.db.query(UserQuestionAnswer)
            .filter(
                and_(
                    UserQuestionAnswer.user_id == user_id,
                    func.date(UserQuestionAnswer.answered_at) == today,
                )
            )
            .count()
        )

        # Correct answers today
        correct_today = (
            self.db.query(UserQuestionAnswer)
            .filter(
                and_(
                    UserQuestionAnswer.user_id == user_id,
                    func.date(UserQuestionAnswer.answered_at) == today,
                    UserQuestionAnswer.is_correct == True,
                )
            )
            .count()
        )

        # Overall accuracy rate
        total_correct = (
            self.db.query(UserQuestionAnswer)
            .filter(
                and_(
                    UserQuestionAnswer.user_id == user_id,
                    UserQuestionAnswer.is_correct == True,
                )
            )
            .count()
        )

        accuracy_rate = total_correct / total_answered if total_answered > 0 else 0

        # Current streak (consecutive days with at least one correct answer)
        streak = self._calculate_streak(user_id)

        # Performance by category
        category_stats = self._get_category_performance(user_id)

        # Favorite category (most answered)
        favorite_category = (
            max(category_stats.keys(), key=lambda k: category_stats[k]["answered"])
            if category_stats
            else None
        )

        return {
            "total_questions": total_answered,
            "answered_today": answered_today,
            "correct_today": correct_today,
            "accuracy_rate": accuracy_rate,
            "streak": streak,
            "favorite_category": favorite_category,
            "categories": category_stats,
        }

    def _calculate_streak(self, user_id: int) -> int:
        """Calculate the current streak of consecutive days with correct answers."""

        # Get dates with correct answers, ordered by date descending
        dates_with_correct = (
            self.db.query(
                func.date(UserQuestionAnswer.answered_at).label("answer_date")
            )
            .filter(
                and_(
                    UserQuestionAnswer.user_id == user_id,
                    UserQuestionAnswer.is_correct == True,
                )
            )
            .distinct()
            .order_by(func.date(UserQuestionAnswer.answered_at).desc())
            .all()
        )

        if not dates_with_correct:
            return 0

        streak = 0
        current_date = datetime.now(timezone.utc).date()

        for row in dates_with_correct:
            answer_date = row.answer_date

            # Check if this date is consecutive
            if (current_date - answer_date).days == streak:
                streak += 1
                current_date = answer_date
            else:
                break

        return streak

    def _get_category_performance(self, user_id: int) -> Dict[str, Dict[str, int]]:
        """Get performance statistics by category."""

        # Get answers with question categories
        results = (
            self.db.query(
                QuickQuestion.category,
                func.count(UserQuestionAnswer.id).label("answered"),
                func.sum(func.cast(UserQuestionAnswer.is_correct, int)).label(
                    "correct"
                ),
            )
            .join(
                UserQuestionAnswer, QuickQuestion.id == UserQuestionAnswer.question_id
            )
            .filter(UserQuestionAnswer.user_id == user_id)
            .group_by(QuickQuestion.category)
            .all()
        )

        category_stats = {}
        for result in results:
            category_name = result.category.value if result.category else "unknown"
            category_stats[category_name] = {
                "answered": result.answered,
                "correct": result.correct or 0,
            }

        return category_stats

    def create_question(self, question_data: Dict[str, Any]) -> QuickQuestion:
        """Create a new question."""

        # Validate category
        try:
            category_enum = QuestionCategory(question_data["category"])
        except ValueError:
            raise ValueError(f"Invalid category: {question_data['category']}")

        question = QuickQuestion(
            question_text=question_data["question_text"],
            correct_answer=question_data["correct_answer"],
            option_a=question_data["option_a"],
            option_b=question_data["option_b"],
            option_c=question_data["option_c"],
            option_d=question_data["option_d"],
            explanation=question_data.get("explanation"),
            category=category_enum,
            difficulty_level=question_data["difficulty_level"],
            source_url=question_data.get("source_url"),
            tags=question_data.get("tags", []),
            is_active=question_data.get("is_active", True),
        )

        self.db.add(question)
        self.db.commit()
        self.db.refresh(question)

        return question

    def get_categories(self) -> List[Dict[str, Any]]:
        """Get available question categories with counts."""

        # Get question counts by category
        category_counts = (
            self.db.query(
                QuickQuestion.category, func.count(QuickQuestion.id).label("count")
            )
            .filter(QuickQuestion.is_active == True)
            .group_by(QuickQuestion.category)
            .all()
        )

        # Create category info
        categories = []
        category_info = {
            QuestionCategory.BUDGET_BASICS: {
                "name": "Budget Basics",
                "description": "Fundamental concepts of government budgeting",
            },
            QuestionCategory.AUDIT_FUNDAMENTALS: {
                "name": "Audit Fundamentals",
                "description": "Understanding government audit processes",
            },
            QuestionCategory.DEBT_MANAGEMENT: {
                "name": "Debt Management",
                "description": "Government debt and borrowing concepts",
            },
            QuestionCategory.FINANCIAL_TRANSPARENCY: {
                "name": "Financial Transparency",
                "description": "Open government and accountability principles",
            },
            QuestionCategory.GOVERNANCE: {
                "name": "Governance",
                "description": "Public sector governance and oversight",
            },
            QuestionCategory.PUBLIC_FINANCE: {
                "name": "Public Finance",
                "description": "Economics of government finance",
            },
        }

        # Convert to response format
        count_dict = {result.category: result.count for result in category_counts}

        for category_enum, info in category_info.items():
            categories.append(
                {
                    "id": category_enum.value,
                    "name": info["name"],
                    "description": info["description"],
                    # zero-fallback-ok: count_dict is a GROUP BY count; a category absent from it has no questions, so 0 is the true count
                    "question_count": count_dict.get(category_enum, 0),
                }
            )

        return categories

    def bulk_import_questions(
        self, questions_data: List[Dict[str, Any]]
    ) -> Dict[str, Any]:
        """Import multiple questions in bulk."""

        created_count = 0
        error_count = 0
        errors = []

        for i, question_data in enumerate(questions_data):
            try:
                self.create_question(question_data)
                created_count += 1
            except Exception as e:
                error_count += 1
                errors.append(f"Question {i+1}: {str(e)}")
                logger.error(f"Error creating question {i+1}: {str(e)}")

        return {
            "created": created_count,
            "errors": error_count,
            "error_details": errors,
        }
