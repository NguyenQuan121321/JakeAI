"""Generate Markdown table of test coverage into GitHub Actions Step Summary."""

import os
import sys
import xml.etree.ElementTree as ET


def main() -> None:
    coverage_file = "coverage.xml"
    if not os.path.exists(coverage_file):
        print(
            f"Coverage file '{coverage_file}' not found. Skipping summary generation."
        )
        return

    try:
        tree = ET.parse(coverage_file)
        root = tree.getroot()
        line_rate = float(root.attrib.get("line-rate", 0)) * 100

        summary = f"### 📊 Backend Test Coverage: **{line_rate:.2f}%** (Quality Gate: ≥85%)\n\n"
        summary += "| Component / Package | Coverage |\n| :--- | :--- |\n"

        for pkg in root.findall(".//package"):
            pname = pkg.attrib.get("name")
            prate = float(pkg.attrib.get("line-rate", 0)) * 100
            summary += f"| `{pname}` | {prate:.2f}% |\n"

        summary += "\n*Quality Gate: ≥85% strictly enforced by pytest-cov.*\n"

        step_summary = os.environ.get("GITHUB_STEP_SUMMARY")
        if step_summary:
            with open(step_summary, "a", encoding="utf-8") as f:
                f.write(summary)
            print("Successfully published coverage summary to GITHUB_STEP_SUMMARY.")
        else:
            print(summary)
    except Exception as exc:
        print(f"Failed to generate coverage summary: {exc}", file=sys.stderr)


if __name__ == "__main__":
    main()
