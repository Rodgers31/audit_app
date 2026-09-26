"""
Kenya Government Finance Question Service
Focuses on Kenya-specific government finance, audit, and transparency questions
"""

import logging
import random
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


class KenyaGovernmentQuestionSource:
    """Generate Kenya-specific government finance questions."""

    def __init__(self):
        self.source_name = "Kenya Government Finance Knowledge Base"
        self.kenya_questions_pool = self._initialize_kenya_questions()

    def _initialize_kenya_questions(self) -> List[Dict[str, Any]]:
        """Initialize comprehensive Kenya government finance questions."""
        return [
            # Kenya Budget Questions
            {
                "question_text": "What is the name of Kenya's annual government budget document?",
                "option_a": "Budget Policy Statement",
                "option_b": "Budget Estimates",
                "option_c": "Appropriation Bill",
                "option_d": "National Budget",
                "correct_answer": "B",
                "explanation": "Budget Estimates is the detailed annual budget document presented to Parliament by the National Treasury.",
                "category": "budget_basics",
                "difficulty_level": 2,
                "tags": ["kenya", "budget", "parliament", "treasury"],
                "source_url": "https://treasury.go.ke",
            },
            {
                "question_text": "Which institution is responsible for preparing Kenya's national budget?",
                "option_a": "Central Bank of Kenya",
                "option_b": "Kenya Revenue Authority",
                "option_c": "National Treasury",
                "option_d": "Ministry of Finance",
                "correct_answer": "C",
                "explanation": "The National Treasury is responsible for preparing Kenya's national budget and fiscal policy.",
                "category": "budget_basics",
                "difficulty_level": 1,
                "tags": ["kenya", "treasury", "budget_preparation"],
            },
            {
                "question_text": "What is the Budget Policy Statement (BPS) in Kenya?",
                "option_a": "The final budget document",
                "option_b": "A preliminary budget framework document",
                "option_c": "The audit report",
                "option_d": "The spending report",
                "correct_answer": "B",
                "explanation": "The BPS outlines the government's fiscal policy framework and budget priorities for the upcoming financial year.",
                "category": "budget_basics",
                "difficulty_level": 3,
                "tags": ["kenya", "BPS", "fiscal_policy", "framework"],
            },
            # Kenya Audit Questions
            {
                "question_text": "Who is the constitutional head of audit in Kenya?",
                "option_a": "Controller of Budget",
                "option_b": "Auditor General",
                "option_c": "Treasury Secretary",
                "option_d": "Comptroller General",
                "correct_answer": "B",
                "explanation": "The Auditor General is the constitutional head of the Kenya National Audit Office (KENAO).",
                "category": "audit_fundamentals",
                "difficulty_level": 2,
                "tags": ["kenya", "auditor_general", "KENAO", "constitution"],
            },
            {
                "question_text": "What does KENAO stand for?",
                "option_a": "Kenya National Accountability Office",
                "option_b": "Kenya National Audit Office",
                "option_c": "Kenya National Assessment Office",
                "option_d": "Kenya National Administrative Office",
                "correct_answer": "B",
                "explanation": "KENAO is the Kenya National Audit Office, the supreme audit institution of Kenya.",
                "category": "audit_fundamentals",
                "difficulty_level": 1,
                "tags": ["kenya", "KENAO", "audit", "institution"],
            },
            # Kenya Financial Management Questions
            {
                "question_text": "What does IFMIS stand for in Kenya's financial management?",
                "option_a": "Integrated Financial Management Information System",
                "option_b": "International Financial Monitoring Information System",
                "option_c": "Internal Financial Management Information System",
                "option_d": "Independent Financial Management Information System",
                "correct_answer": "A",
                "explanation": "IFMIS is Kenya's Integrated Financial Management Information System for government financial operations.",
                "category": "financial_transparency",
                "difficulty_level": 2,
                "tags": ["kenya", "IFMIS", "financial_management", "technology"],
            },
            {
                "question_text": "Which law governs public financial management in Kenya?",
                "option_a": "Public Procurement Act",
                "option_b": "Public Finance Management Act",
                "option_c": "Public Service Act",
                "option_d": "Public Audit Act",
                "correct_answer": "B",
                "explanation": "The Public Finance Management (PFM) Act, 2012 is the primary law governing public financial management in Kenya.",
                "category": "governance",
                "difficulty_level": 2,
                "tags": ["kenya", "PFM_act", "2012", "legal_framework"],
            },
            {
                "question_text": "What is the role of the Controller of Budget in Kenya?",
                "option_a": "To prepare the national budget",
                "option_b": "To authorize government expenditure",
                "option_c": "To audit government accounts",
                "option_d": "To collect government revenue",
                "correct_answer": "B",
                "explanation": "The Controller of Budget authorizes withdrawals from government accounts and ensures spending is within approved budgets.",
                "category": "governance",
                "difficulty_level": 3,
                "tags": [
                    "kenya",
                    "controller_of_budget",
                    "expenditure",
                    "authorization",
                ],
            },
            # Kenya Debt Management Questions
            {
                "question_text": "What is Kenya's debt ceiling as per the PFM Act?",
                "option_a": "40% of GDP",
                "option_b": "50% of GDP",
                "option_c": "60% of GDP",
                "option_d": "70% of GDP",
                "correct_answer": "B",
                "explanation": "Kenya's debt ceiling is set at 50% of GDP as stipulated in the Public Finance Management Act.",
                "category": "debt_management",
                "difficulty_level": 4,
                "tags": ["kenya", "debt_ceiling", "50_percent", "GDP", "PFM_act"],
            },
            {
                "question_text": "Which institution manages Kenya's public debt?",
                "option_a": "Central Bank of Kenya",
                "option_b": "National Treasury",
                "option_c": "Kenya Revenue Authority",
                "option_d": "Ministry of Finance",
                "correct_answer": "B",
                "explanation": "The National Treasury is responsible for managing Kenya's public debt including borrowing and debt servicing.",
                "category": "debt_management",
                "difficulty_level": 2,
                "tags": ["kenya", "treasury", "public_debt", "management"],
            },
            # Kenya Revenue and Taxation Questions
            {
                "question_text": "What does KRA stand for in Kenya?",
                "option_a": "Kenya Revenue Authority",
                "option_b": "Kenya Registration Authority",
                "option_c": "Kenya Regulatory Authority",
                "option_d": "Kenya Research Authority",
                "correct_answer": "A",
                "explanation": "KRA is the Kenya Revenue Authority, responsible for tax administration and revenue collection.",
                "category": "public_finance",
                "difficulty_level": 1,
                "tags": ["kenya", "KRA", "revenue", "tax_administration"],
            },
            {
                "question_text": "What is VAT rate in Kenya as of 2024?",
                "option_a": "14%",
                "option_b": "16%",
                "option_c": "18%",
                "option_d": "20%",
                "correct_answer": "B",
                "explanation": "Kenya's standard VAT (Value Added Tax) rate is 16% as of 2024.",
                "category": "public_finance",
                "difficulty_level": 2,
                "tags": ["kenya", "VAT", "16_percent", "taxation", "2024"],
            },
            # Kenya County Government Questions
            {
                "question_text": "What percentage of national revenue is allocated to county governments in Kenya?",
                "option_a": "At least 15%",
                "option_b": "At least 20%",
                "option_c": "At least 25%",
                "option_d": "At least 30%",
                "correct_answer": "A",
                "explanation": "The Constitution requires at least 15% of national revenue to be allocated to county governments.",
                "category": "governance",
                "difficulty_level": 3,
                "tags": [
                    "kenya",
                    "counties",
                    "15_percent",
                    "devolution",
                    "constitution",
                ],
            },
            {
                "question_text": "How many county governments are there in Kenya?",
                "option_a": "45",
                "option_b": "47",
                "option_c": "49",
                "option_d": "52",
                "correct_answer": "B",
                "explanation": "Kenya has 47 county governments established under the 2010 Constitution.",
                "category": "governance",
                "difficulty_level": 1,
                "tags": ["kenya", "47_counties", "devolution", "2010_constitution"],
            },
            # Kenya Parliamentary Budget Office Questions
            {
                "question_text": "What is the role of the Parliamentary Budget Office (PBO) in Kenya?",
                "option_a": "To prepare the national budget",
                "option_b": "To provide independent budget analysis to Parliament",
                "option_c": "To audit government expenditure",
                "option_d": "To collect government revenue",
                "correct_answer": "B",
                "explanation": "The PBO provides independent, objective analysis of budget and economic issues to Parliament.",
                "category": "governance",
                "difficulty_level": 3,
                "tags": [
                    "kenya",
                    "PBO",
                    "parliament",
                    "budget_analysis",
                    "independent",
                ],
            },
            # Kenya Procurement Questions
            {
                "question_text": "Which law governs public procurement in Kenya?",
                "option_a": "Public Procurement and Asset Disposal Act",
                "option_b": "Public Finance Management Act",
                "option_c": "Public Audit Act",
                "option_d": "Public Service Act",
                "correct_answer": "A",
                "explanation": "The Public Procurement and Asset Disposal Act, 2015 governs public procurement in Kenya.",
                "category": "governance",
                "difficulty_level": 2,
                "tags": ["kenya", "procurement", "PPADA", "2015"],
            },
            # Kenya Transparency and Access to Information
            {
                "question_text": "What is the Access to Information Act in Kenya about?",
                "option_a": "Controlling information flow",
                "option_b": "Providing citizens right to government information",
                "option_c": "Restricting media access",
                "option_d": "Managing government databases",
                "correct_answer": "B",
                "explanation": "The Access to Information Act, 2016 gives citizens the right to access information held by public entities.",
                "category": "financial_transparency",
                "difficulty_level": 2,
                "tags": [
                    "kenya",
                    "ATI_act",
                    "2016",
                    "citizen_rights",
                    "information_access",
                ],
            },
            # Additional Kenya-specific questions
            {
                "question_text": "What is the Medium Term Expenditure Framework (MTEF) in Kenya?",
                "option_a": "A quarterly budget review",
                "option_b": "A three-year budget planning framework",
                "option_c": "An annual audit report",
                "option_d": "A monthly expenditure report",
                "correct_answer": "B",
                "explanation": "MTEF is Kenya's three-year budget planning framework that links policy, planning and budgeting.",
                "category": "budget_basics",
                "difficulty_level": 4,
                "tags": ["kenya", "MTEF", "three_year", "planning", "framework"],
            },
            {
                "question_text": "What is the Constituency Development Fund (CDF) in Kenya?",
                "option_a": "A fund for county development",
                "option_b": "A fund for constituency-level development projects",
                "option_c": "A fund for national projects",
                "option_d": "A fund for ward development",
                "correct_answer": "B",
                "explanation": "CDF allocates funds to each constituency for development projects at the grassroots level.",
                "category": "governance",
                "difficulty_level": 2,
                "tags": ["kenya", "CDF", "constituency", "grassroots", "development"],
            },
        ]

    def fetch_questions(
        self, category: Optional[str] = None, limit: int = 10
    ) -> List[Dict[str, Any]]:
        """Fetch Kenya-specific government finance questions."""
        try:
            # Filter by category if specified
            questions = self.kenya_questions_pool.copy()
            if category:
                questions = [q for q in questions if q["category"] == category]

            # Randomize and limit
            # nondeterminism-ok: which quiz questions to show; a selection of questions, not a figure
            random.shuffle(questions)
            return questions[:limit]

        except Exception as e:
            logger.error(f"Error fetching Kenya questions: {str(e)}")
            return []


class QuestionAggregatorService:
    """Service to aggregate questions from Kenya-focused sources."""

    def __init__(self):
        self.kenya_source = KenyaGovernmentQuestionSource()

    def fetch_daily_questions(
        self,
        category: Optional[str] = None,
        difficulty_level: Optional[int] = None,
        limit: int = 10,
    ) -> List[Dict[str, Any]]:
        """Fetch daily questions from Kenya-focused sources."""

        # Get questions from Kenya source
        all_questions = self.kenya_source.fetch_questions(
            category=category, limit=limit * 2
        )

        # Filter by difficulty if specified
        if difficulty_level:
            all_questions = [
                q
                for q in all_questions
                if q.get("difficulty_level") == difficulty_level
            ]

        # Randomize and limit final results
        # nondeterminism-ok: which quiz questions to show; a selection of questions, not a figure
        random.shuffle(all_questions)
        return all_questions[:limit]

    def get_question_sources_status(self) -> Dict[str, Any]:
        """Get status of question sources."""

        try:
            # Test fetch questions
            test_questions = self.kenya_source.fetch_questions(limit=1)
            operational = len(test_questions) > 0

            return {
                "sources": [
                    {
                        "name": self.kenya_source.source_name,
                        "status": "operational" if operational else "no_questions",
                        "question_count": len(self.kenya_source.kenya_questions_pool),
                    }
                ],
                "total_sources": 1,
                "operational_sources": 1 if operational else 0,
            }
        except Exception as e:
            return {
                "sources": [
                    {
                        "name": self.kenya_source.source_name,
                        "status": "error",
                        "error": str(e),
                    }
                ],
                "total_sources": 1,
                "operational_sources": 0,
            }

    def update_questions_from_sources(self) -> Dict[str, Any]:
        """Update questions from sources and return summary."""

        try:
            questions = self.kenya_source.fetch_questions(limit=50)

            return {
                "success": True,
                "questions_updated": len(questions),
                "sources_updated": [self.kenya_source.source_name],
                "errors": 0,
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "note": "Kenya-specific questions are maintained locally and updated through this service",
            }

        except Exception as e:
            logger.error(f"Error updating questions: {str(e)}")
            return {
                "success": False,
                "questions_updated": 0,
                "sources_updated": [],
                "errors": 1,
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "error_detail": str(e),
            }
