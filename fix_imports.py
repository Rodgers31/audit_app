#!/usr/bin/env python3
"""
Fix Import Statements
Updates import paths in moved files to reflect new project structure
"""

import os
import re


def update_file_imports(file_path, import_updates):
    """Update import statements in a file."""
    if not os.path.exists(file_path):
        return False

    with open(file_path, "r") as f:
        content = f.read()

    updated = False
    for old_import, new_import in import_updates.items():
        if old_import in content:
            content = content.replace(old_import, new_import)
            updated = True
            print(f"   ✅ Updated: {old_import} -> {new_import}")

    if updated:
        with open(file_path, "w") as f:
            f.write(content)
        return True
    return False


def fix_api_imports():
    """Fix import statements in API files."""
    print("🔧 FIXING API IMPORT STATEMENTS")
    print("=" * 31)

    # Modernized API
    modernized_file = "apis/modernized_api.py"
    if os.path.exists(modernized_file):
        # Need to update the analytics import
        with open(modernized_file, "r") as f:
            content = f.read()

        # Update the analytics import
        if "from data_driven_analytics import" in content:
            content = content.replace(
                "from data_driven_analytics import",
                'import sys\nsys.path.append("../analysis")\nfrom data_driven_analytics import',
            )
            with open(modernized_file, "w") as f:
                f.write(content)
            print(f"📝 Updated: {modernized_file}")


def fix_analysis_imports():
    """Fix import statements in analysis files."""
    print("\n🔧 FIXING ANALYSIS IMPORT STATEMENTS")
    print("=" * 35)

    # Data Driven Analytics
    analytics_file = "analysis/data_driven_analytics.py"
    if os.path.exists(analytics_file):
        import_updates = {
            "enhanced_county_data.json": "../data/county/enhanced_county_data.json",
            "oag_audit_data.json": "../data/audit/oag_audit_data.json",
            "comprehensive_cob_reports_database.json": "../data/cob/comprehensive_cob_reports_database.json",
            "comprehensive_government_reports.json": "../data/government/comprehensive_government_reports.json",
            "ultimate_etl_results.json": "../data/government/ultimate_etl_results.json",
        }
        if update_file_imports(analytics_file, import_updates):
            print(f"📝 Updated: {analytics_file}")

    # County Data Analyzer
    analyzer_file = "analysis/county_data_analyzer.py"
    if os.path.exists(analyzer_file):
        import_updates = {
            "enhanced_county_data.json": "../data/county/enhanced_county_data.json"
        }
        if update_file_imports(analyzer_file, import_updates):
            print(f"📝 Updated: {analyzer_file}")


def create_import_helper():
    """Create a helper script to manage imports."""
    print("\n📝 CREATING IMPORT HELPER")
    print("=" * 24)

    helper_content = '''#!/usr/bin/env python3
"""
Import Helper for Organized Project Structure
Provides easy access to data files from any location
"""

import os
from pathlib import Path

class DataPaths:
    """Centralized data file paths for the organized project."""
    
    def __init__(self):
        # Get the project root directory
        self.project_root = Path(__file__).parent
        
    def get_county_data_path(self):
        """Get path to enhanced county data."""
        return self.project_root / "data" / "county" / "enhanced_county_data.json"
    
    def get_audit_data_path(self):
        """Get path to OAG audit data."""
        return self.project_root / "data" / "audit" / "oag_audit_data.json"
    
    def get_cob_data_path(self):
        """Get path to COB reports database."""
        return self.project_root / "data" / "cob" / "comprehensive_cob_reports_database.json"
    
    def get_government_reports_path(self):
        """Get path to government reports."""
        return self.project_root / "data" / "government" / "comprehensive_government_reports.json"
    
    def get_etl_results_path(self):
        """Get path to ETL results."""
        return self.project_root / "data" / "government" / "ultimate_etl_results.json"

# Global instance for easy importing
data_paths = DataPaths()

# Convenience functions
def load_county_data():
    """Load county data JSON."""
    import json
    with open(data_paths.get_county_data_path(), 'r') as f:
        return json.load(f)

def load_audit_data():
    """Load audit data JSON."""
    import json
    with open(data_paths.get_audit_data_path(), 'r') as f:
        return json.load(f)

def load_cob_data():
    """Load COB data JSON."""
    import json
    with open(data_paths.get_cob_data_path(), 'r') as f:
        return json.load(f)
'''

    with open("data_helper.py", "w") as f:
        f.write(helper_content)

    print("✅ Created: data_helper.py")


def run_import_fixes():
    """Run all import fixes."""
    print("🚀 FIXING IMPORT STATEMENTS")
    print("=" * 27)

    fix_api_imports()
    fix_analysis_imports()
    create_import_helper()

    print("\n✅ IMPORT FIXES COMPLETE!")
    print("\n📝 NEXT STEPS:")
    print("2. Test analysis: cd analysis && python county_data_analyzer.py")
    print("3. Use data_helper.py for easy data access in new files")


if __name__ == "__main__":
    run_import_fixes()
