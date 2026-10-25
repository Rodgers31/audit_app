import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

# Handle missing dependencies gracefully
try:
    import camelot

    HAS_CAMELOT = True
except ImportError:
    HAS_CAMELOT = False
    camelot = None

try:
    import pandas as pd

    HAS_PANDAS = True
except ImportError:
    HAS_PANDAS = False
    pd = None

try:
    import pdfplumber

    HAS_PDFPLUMBER = True
except ImportError:
    HAS_PDFPLUMBER = False
    pdfplumber = None

try:
    import tabula

    HAS_TABULA = True
except ImportError:
    HAS_TABULA = False
    tabula = None

# Support both package and script imports
try:
    from .source_registry import registry
except Exception:  # pragma: no cover
    from source_registry import registry

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class DocumentExtractor:
    """Extract structured data from government documents."""

    def __init__(self):
        self.extractors = {
            "pdfplumber": self._extract_with_pdfplumber,
            "camelot": self._extract_with_camelot,
            "tabula": self._extract_with_tabula,
        }

    def _extract_with_pdfplumber(self, file_path: str) -> Dict[str, Any]:
        """Extract text and basic table data using pdfplumber."""
        extracted_data = {
            "extractor": "pdfplumber",
            "pages": [],
            "tables": [],
            "confidence": 0.7,
        }

        try:
            with pdfplumber.open(file_path) as pdf:
                for page_num, page in enumerate(pdf.pages, 1):
                    page_data = {
                        "page_number": page_num,
                        "text": page.extract_text() or "",
                        "tables": [],
                    }

                    # Extract tables from page
                    tables = page.extract_tables()
                    for table_idx, table in enumerate(tables):
                        if table:
                            table_data = {
                                "table_index": table_idx,
                                "headers": table[0] if table else [],
                                "rows": table[1:] if len(table) > 1 else [],
                                "row_count": len(table) - 1 if len(table) > 1 else 0,
                            }
                            page_data["tables"].append(table_data)
                            extracted_data["tables"].append(
                                {
                                    "page": page_num,
                                    "table_index": table_idx,
                                    "data": table_data,
                                }
                            )

                    extracted_data["pages"].append(page_data)

            logger.info(
                f"Extracted {len(extracted_data['pages'])} pages and {len(extracted_data['tables'])} tables from {file_path}"
            )

        except Exception as e:
            logger.error(f"PDFPlumber extraction failed for {file_path}: {e}")
            extracted_data["error"] = str(e)
            extracted_data["confidence"] = 0.0

        return extracted_data

    def _extract_with_camelot(self, file_path: str) -> Dict[str, Any]:
        """Extract tables using Camelot (better for complex tables)."""
        extracted_data = {"extractor": "camelot", "tables": [], "confidence": 0.8}

        try:
            # Extract tables from all pages
            # Preserve the existing raster lattice policy across Camelot 2's
            # default switch to combined raster/vector detection.
            tables = camelot.read_pdf(
                file_path, pages="all", flavor="lattice", engine="raster"
            )

            for table_idx, table in enumerate(tables):
                table_data = {
                    "table_index": table_idx,
                    "page": table.page,
                    "confidence": table.parsing_report.get("accuracy", 0),
                    "headers": table.df.columns.tolist(),
                    "rows": table.df.values.tolist(),
                    "row_count": len(table.df),
                }
                extracted_data["tables"].append(table_data)

            # Calculate average confidence
            if extracted_data["tables"]:
                avg_confidence = sum(
                    t["confidence"] for t in extracted_data["tables"]
                ) / len(extracted_data["tables"])
                extracted_data["confidence"] = (
                    avg_confidence / 100
                )  # Convert to 0-1 scale

            logger.info(
                f"Camelot extracted {len(extracted_data['tables'])} tables from {file_path}"
            )

        except Exception as e:
            logger.error(f"Camelot extraction failed for {file_path}: {e}")
            extracted_data["error"] = str(e)
            extracted_data["confidence"] = 0.0

        return extracted_data

    def _extract_with_tabula(self, file_path: str) -> Dict[str, Any]:
        """Extract tables using Tabula (good for simple tables)."""
        extracted_data = {"extractor": "tabula", "tables": [], "confidence": 0.6}

        try:
            # Extract tables from all pages
            tables = tabula.read_pdf(file_path, pages="all", multiple_tables=True)

            for table_idx, df in enumerate(tables):
                if not df.empty:
                    table_data = {
                        "table_index": table_idx,
                        "headers": df.columns.tolist(),
                        "rows": df.values.tolist(),
                        "row_count": len(df),
                    }
                    extracted_data["tables"].append(table_data)

            logger.info(
                f"Tabula extracted {len(extracted_data['tables'])} tables from {file_path}"
            )

        except Exception as e:
            logger.error(f"Tabula extraction failed for {file_path}: {e}")
            extracted_data["error"] = str(e)
            extracted_data["confidence"] = 0.0

        return extracted_data

    def extract_document(
        self, file_path: str, extractor: str = "pdfplumber"
    ) -> Dict[str, Any]:
        """Extract data from a document using specified extractor."""
        if extractor not in self.extractors:
            raise ValueError(f"Unknown extractor: {extractor}")

        extraction_result = self.extractors[extractor](file_path)
        extraction_result.update(
            {
                "file_path": file_path,
                "extraction_date": datetime.now().isoformat(),
                "file_size": (
                    Path(file_path).stat().st_size if Path(file_path).exists() else 0
                ),
            }
        )

        return extraction_result

    def extract_with_fallback(self, file_path: str) -> Dict[str, Any]:
        """Try multiple extractors and return the best result."""
        extractors_to_try = []
        if HAS_CAMELOT:
            extractors_to_try.append("camelot")
        if HAS_PDFPLUMBER:
            extractors_to_try.append("pdfplumber")
        if HAS_TABULA:
            extractors_to_try.append("tabula")
        if not extractors_to_try:
            # Nothing available; return minimal stub
            return {
                "extractor": "none",
                "error": "No PDF extractors available",
                "confidence": 0.0,
                "file_path": file_path,
                "extraction_date": datetime.now().isoformat(),
            }
        best_result = None
        best_confidence = 0

        for extractor in extractors_to_try:
            try:
                result = self.extract_document(file_path, extractor)
                confidence = result.get("confidence", 0)

                if confidence > best_confidence:
                    best_confidence = confidence
                    best_result = result

            except Exception as e:
                logger.warning(f"Extractor {extractor} failed for {file_path}: {e}")

        if best_result is None:
            # Return empty result if all extractors failed
            best_result = {
                "extractor": "none",
                "error": "All extractors failed",
                "confidence": 0.0,
                "file_path": file_path,
                "extraction_date": datetime.now().isoformat(),
            }

        return best_result

    def save_extraction(self, extraction_data: Dict[str, Any], output_path: str):
        """Save extraction results to JSON file."""
        with open(output_path, "w") as f:
            json.dump(extraction_data, f, indent=2, default=str)

    def extract_batch(
        self, file_list: List[str], output_dir: str = "extractions"
    ) -> List[Dict[str, Any]]:
        """Extract data from multiple files."""
        output_path = Path(output_dir)
        output_path.mkdir(exist_ok=True)

        results = []

        for file_path in file_list:
            logger.info(f"Extracting from {file_path}")

            extraction = self.extract_with_fallback(file_path)

            # Save individual extraction
            file_name = Path(file_path).stem
            output_file = output_path / f"{file_name}_extraction.json"
            self.save_extraction(extraction, str(output_file))

            results.append(extraction)

        return results


if __name__ == "__main__":
    extractor = DocumentExtractor()

    # Example usage
    downloads_dir = Path("downloads")
    if downloads_dir.exists():
        pdf_files = list(downloads_dir.glob("*.pdf"))
        if pdf_files:
            extractions = extractor.extract_batch(
                [str(f) for f in pdf_files[:3]]
            )  # Test first 3 files
            print(f"Extracted data from {len(extractions)} files")
