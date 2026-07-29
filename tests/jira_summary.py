import json
from pathlib import Path
from typing import Any, Dict, List


def extract_text(node: Any) -> str:
    if isinstance(node, str):
        return node
    if isinstance(node, list):
        return "".join(extract_text(child) for child in node)
    if isinstance(node, dict):
        text = ""
        if node.get("type") == "text":
            text += node.get("text", "")
        for key in ["content", "contentInlined", "contentStrings"]:
            if key in node:
                text += extract_text(node[key])
        return text
    return ""


def extract_description(fields: Dict[str, Any]) -> str:
    description = fields.get("description")
    if not description:
        return ""
    return extract_text(description.get("content", []))


def extract_acceptance_criteria(description: str) -> str:
    marker = "Acceptance criteria"
    lower = description.lower()
    idx = lower.find(marker.lower())
    if idx == -1:
        return ""
    return description[idx:].strip()


def priority_score(issue: Dict[str, Any]) -> int:
    summary = issue["fields"].get("summary", "").lower()
    key = issue.get("key", "")
    if any(term in summary for term in ["closure", "readme", "deploy", "report", "credit", "cost"]):
        return 10
    if any(term in summary for term in ["trace", "alert", "decoupling", "queue", "durability"]):
        return 20
    if any(term in summary for term in ["architecture decision record", "adr", "topology", "traffic", "isolation"]):
        return 30
    if key.startswith("VOR-5"):
        return 15
    return 50


def summarize_issues(data: Dict[str, Any]) -> None:
    issues = data.get("issues", [])
    if not issues:
        print("No issues found in tests/jira_issues.json.")
        return

    print(f"Found {len(issues)} assigned VOR issue(s).\n")

    sorted_issues = sorted(issues, key=lambda issue: (priority_score(issue), issue.get("key", "")))

    print("Prioritized execution order:")
    for pos, issue in enumerate(sorted_issues, start=1):
        key = issue.get("key")
        summary = issue["fields"].get("summary", "")
        status = issue["fields"].get("status", {}).get("name", "")
        print(f"{pos}. {key} — {summary} — {status}")
    print("\nDetails per issue:\n")

    for issue in sorted_issues:
        key = issue.get("key")
        fields = issue["fields"]
        summary = fields.get("summary", "")
        status = fields.get("status", {}).get("name", "")
        labels = fields.get("labels", [])
        updated = fields.get("updated", "")
        description = extract_description(fields)
        acceptance = extract_acceptance_criteria(description)

        print(f"{key}: {summary}")
        print(f"  Status: {status}")
        if labels:
            print(f"  Labels: {', '.join(labels)}")
        if updated:
            print(f"  Updated: {updated}")
        if acceptance:
            print(f"  Acceptance criteria: {acceptance}")
        else:
            print(f"  Acceptance criteria: (not found in description)")
        print()


if __name__ == "__main__":
    path = Path("tests/jira_issues.json")
    if not path.exists():
        raise SystemExit("Error: tests/jira_issues.json not found. Run tests/jira_fetch.py first.")
    data = json.loads(path.read_text(encoding="utf-8"))
    summarize_issues(data)
