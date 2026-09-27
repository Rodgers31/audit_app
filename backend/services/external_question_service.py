"""
Kenya Government Finance Question Service
Focuses on Kenya-specific government finance, audit, and transparency questions
"""

import json
import logging
import random
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

import requests

logger = logging.getLogger(__name__)


class ExternalQuestionSource:
    """Base class for external question sources."""

    def __init__(self, source_name: str):
        self.source_name = source_name

    def fetch_questions(
        self, category: Optional[str] = None, limit: int = 10
    ) -> List[Dict[str, Any]]:
        """Fetch questions from external source."""
        raise NotImplementedError


class KenyaGovernmentQuestionSource(ExternalQuestionSource):
    """Generate Kenya-specific government finance questions."""

    def __init__(self):
        super().__init__("Kenya Government Finance Knowledge Base")
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
                "question_text": "Who is the current constitutional head of audit in Kenya?",
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
            {
                "question_text": "What is the Public Audit Act in Kenya?",
                "option_a": "A law governing public procurement",
                "option_b": "A law governing public audit functions",
                "option_c": "A law governing public finance",
                "option_d": "A law governing public service",
                "correct_answer": "B",
                "explanation": "The Public Audit Act, 2015 provides the legal framework for public audit in Kenya.",
                "category": "audit_fundamentals",
                "difficulty_level": 3,
                "tags": ["kenya", "public_audit_act", "legal_framework", "2015"],
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
        """Fetch questions from Open Trivia Database."""
        try:
            params = {
                "amount": min(limit, 50),  # API limit is 50
                "type": "multiple",  # Multiple choice questions
                # nondeterminism-ok: request parameter asking the Open Trivia API for a difficulty; not published
                "difficulty": random.choice(["easy", "medium", "hard"]),
            }

            # Add category if specified and mapped
            if category and category in self.category_mapping:
                params["category"] = self.category_mapping[category]

            response = requests.get(self.base_url, params=params, timeout=10)
            if response.status_code != 200:
                logger.error(
                    f"Failed to fetch from Open Trivia: {response.status_code}"
                )
                return []

            data = response.json()
            if data.get("response_code") != 0:
                logger.warning(f"Open Trivia API error: {data.get('response_code')}")
                return []

            questions = []
            for item in data.get("results", []):
                # Convert to our format
                incorrect_answers = item.get("incorrect_answers", [])
                correct_answer = item.get("correct_answer", "")

                # Create options A, B, C, D
                all_answers = incorrect_answers + [correct_answer]
                # nondeterminism-ok: quiz answer order, shuffled so the correct letter varies; not a figure
                random.shuffle(all_answers)

                correct_index = all_answers.index(correct_answer)
                correct_letter = chr(65 + correct_index)  # A, B, C, D

                question = {
                    "question_text": self._clean_text(item.get("question", "")),
                    "option_a": self._clean_text(all_answers[0]),
                    "option_b": self._clean_text(all_answers[1]),
                    "option_c": self._clean_text(all_answers[2]),
                    "option_d": self._clean_text(all_answers[3]),
                    "correct_answer": correct_letter,
                    "explanation": f"This question is about {item.get('category', 'general knowledge')}.",
                    "category": category or "public_finance",
                    "difficulty_level": self._map_difficulty(
                        item.get("difficulty", "medium")
                    ),
                    "source_url": "https://opentdb.com/",
                    "tags": [
                        item.get("category", "").lower().replace(" ", "_"),
                        "trivia",
                    ],
                }
                questions.append(question)

            logger.info(f"Fetched {len(questions)} questions from Open Trivia")
            return questions

        except Exception as e:
            logger.error(f"Error fetching from Open Trivia: {str(e)}")
            return []

    def _clean_text(self, text: str) -> str:
        """Clean HTML entities and formatting from text."""
        import html

        return html.unescape(text)

    def _map_difficulty(self, difficulty: str) -> int:
        """Map Open Trivia difficulty to our 1-5 scale."""
        mapping = {"easy": 2, "medium": 3, "hard": 4}
        return mapping.get(difficulty, 3)


# Alias: KenyaGovernmentQuestionSource also fetches from Open Trivia Database
OpenTriviaSource = KenyaGovernmentQuestionSource


class WorldBankSource(ExternalQuestionSource):
    """Generate questions based on World Bank open data."""

    def __init__(self):
        super().__init__("World Bank Data")
        self.base_url = "https://api.worldbank.org/v2"

    def fetch_questions(
        self, category: Optional[str] = None, limit: int = 10
    ) -> List[Dict[str, Any]]:
        """Generate questions from World Bank indicators."""
        try:
            # Sample World Bank indicators related to governance and finance
            indicators = [
                "GC.REV.XGRT.GD.ZS",  # Revenue, excluding grants (% of GDP)
                "GC.XPN.TOTL.GD.ZS",  # Expense (% of GDP)
                "GC.NFN.TOTL.GD.ZS",  # Net incurrence of liabilities, total (% of GDP)
            ]

            questions = []
            for i in range(min(limit, len(indicators) * 3)):
                # nondeterminism-ok: which quiz question to ask next; not a figure
                indicator = random.choice(indicators)

                # Generate a question about this indicator
                question = self._generate_indicator_question(indicator)
                if question:
                    questions.append(question)

            logger.info(f"Generated {len(questions)} questions from World Bank data")
            return questions

        except Exception as e:
            logger.error(f"Error generating World Bank questions: {str(e)}")
            return []

    def _generate_indicator_question(self, indicator: str) -> Optional[Dict[str, Any]]:
        """Generate a question about a specific World Bank indicator."""
        indicator_info = {
            "GC.REV.XGRT.GD.ZS": {
                "name": "government revenue",
                "description": "Government revenue excluding grants as percentage of GDP",
            },
            "GC.XPN.TOTL.GD.ZS": {
                "name": "government expenditure",
                "description": "Government expenses as percentage of GDP",
            },
            "GC.NFN.TOTL.GD.ZS": {
                "name": "government borrowing",
                "description": "Net incurrence of government liabilities as percentage of GDP",
            },
        }

        info = indicator_info.get(indicator)
        if not info:
            return None

        questions_templates = [
            {
                "question": f"What does '{info['name']}' typically measure in public finance?",
                "correct": info["description"],
                "incorrect": [
                    "Private sector investment levels",
                    "Foreign exchange reserves",
                    "Inflation rate calculations",
                ],
            },
            {
                "question": f"When analyzing {info['name']}, what is the most important comparison?",
                "correct": "As a percentage of GDP",
                "incorrect": [
                    "In absolute dollar amounts only",
                    "Per capita calculations only",
                    "Compared to private spending only",
                ],
            },
        ]

        # nondeterminism-ok: which quiz question to ask next; not a figure
        template = random.choice(questions_templates)
        all_answers = [template["correct"]] + template["incorrect"]
        # nondeterminism-ok: quiz answer order, shuffled so the correct letter varies; not a figure
        random.shuffle(all_answers)

        correct_index = all_answers.index(template["correct"])
        correct_letter = chr(65 + correct_index)

        return {
            "question_text": template["question"],
            "option_a": all_answers[0],
            "option_b": all_answers[1],
            "option_c": all_answers[2],
            "option_d": all_answers[3] if len(all_answers) > 3 else "None of the above",
            "correct_answer": correct_letter,
            "explanation": f"This relates to {info['description']} and is important for fiscal analysis.",
            "category": "public_finance",
            "difficulty_level": 3,
            "source_url": f"https://data.worldbank.org/indicator/{indicator}",
            "tags": ["world_bank", "indicators", "fiscal_data"],
        }


class KenyaGovernmentSource(ExternalQuestionSource):
    """Generate questions from Kenya government data sources."""

    def __init__(self):
        super().__init__("Kenya Government")
        self.treasury_url = "https://treasury.go.ke"
        self.cob_url = "https://cob.treasury.go.ke"

    def fetch_questions(
        self, category: Optional[str] = None, limit: int = 10
    ) -> List[Dict[str, Any]]:
        """Generate Kenya-specific questions."""
        # Pre-generated Kenya-specific questions based on actual government structure
        kenya_questions = [
            {
                "question_text": "Which ministry is responsible for budget preparation in Kenya?",
                "option_a": "Ministry of Interior",
                "option_b": "The National Treasury and Planning",
                "option_c": "Ministry of Public Service",
                "option_d": "Office of the President",
                "correct_answer": "B",
                "explanation": "The National Treasury and Planning is responsible for budget preparation, economic planning, and financial management in Kenya.",
                "category": "governance",
                "difficulty_level": 2,
                "source_url": "https://treasury.go.ke",
                "tags": ["kenya", "budget", "treasury", "government_structure"],
            },
            {
                "question_text": "What is the Controller of Budget's main responsibility in Kenya?",
                "option_a": "Preparing the national budget",
                "option_b": "Collecting taxes",
                "option_c": "Authorizing government expenditure",
                "option_d": "Auditing government accounts",
                "correct_answer": "C",
                "explanation": "The Controller of Budget authorizes withdrawals from public funds and ensures spending aligns with approved budgets.",
                "category": "governance",
                "difficulty_level": 3,
                "source_url": "https://cob.treasury.go.ke",
                "tags": ["kenya", "controller_of_budget", "expenditure", "oversight"],
            },
            {
                "question_text": "When does Kenya's financial year typically start?",
                "option_a": "January 1st",
                "option_b": "April 1st",
                "option_c": "July 1st",
                "option_d": "October 1st",
                "correct_answer": "C",
                "explanation": "Kenya's financial year runs from July 1st to June 30th of the following year.",
                "category": "budget_basics",
                "difficulty_level": 2,
                "source_url": "https://treasury.go.ke",
                "tags": ["kenya", "financial_year", "budget_cycle"],
            },
            {
                "question_text": "What does IFMIS stand for in Kenya's public finance system?",
                "option_a": "Internal Financial Management Information System",
                "option_b": "Integrated Financial Management Information System",
                "option_c": "International Finance Monitoring and Information System",
                "option_d": "Independent Financial Management and Internal Systems",
                "correct_answer": "B",
                "explanation": "IFMIS is the Integrated Financial Management Information System used to manage government financial transactions in Kenya.",
                "category": "governance",
                "difficulty_level": 4,
                "source_url": "https://treasury.go.ke",
                "tags": ["kenya", "ifmis", "financial_management", "technology"],
            },
        ]

        # Return random selection up to the limit
        # nondeterminism-ok: which quiz questions to show; a selection of questions, not a figure
        selected = random.sample(kenya_questions, min(limit, len(kenya_questions)))
        logger.info(f"Generated {len(selected)} Kenya-specific questions")
        return selected


class QuestionAggregatorService:
    """Main service that aggregates questions from multiple sources."""

    def __init__(self):
        self.sources = [
            OpenTriviaSource(),
            WorldBankSource(),
            KenyaGovernmentSource(),
        ]

    def fetch_new_questions(
        self,
        category: Optional[str] = None,
        total_limit: int = 20,
        source_distribution: Optional[Dict[str, int]] = None,
    ) -> List[Dict[str, Any]]:
        """Fetch questions from all sources."""

        if source_distribution is None:
            # Default distribution
            source_distribution = {
                "Kenya Government": 8,  # Prioritize local content
                "World Bank Data": 7,
                "Open Trivia Database": 5,
            }

        all_questions = []

        for source in self.sources:
            limit_for_source = source_distribution.get(source.source_name, 5)
            try:
                questions = source.fetch_questions(category, limit_for_source)
                for q in questions:
                    q["source"] = source.source_name
                    q["fetched_at"] = datetime.now(timezone.utc).isoformat()
                all_questions.extend(questions)

            except Exception as e:
                logger.error(f"Error fetching from {source.source_name}: {str(e)}")
                continue

        # Shuffle and limit total
        # nondeterminism-ok: which quiz questions to show; a selection of questions, not a figure
        random.shuffle(all_questions)
        return all_questions[:total_limit]

    def get_available_sources(self) -> List[Dict[str, str]]:
        """Get list of available question sources."""
        return [
            {"name": source.source_name, "type": type(source).__name__}
            for source in self.sources
        ]
