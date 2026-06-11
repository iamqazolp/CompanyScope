import json
import sys
import os

def main():
    if len(sys.argv) < 2:
        print("Usage: python check_thresholds.py <report.json>")
        sys.exit(1)

    report_path = sys.argv[1]
    
    if not os.path.exists(report_path):
        print(f"Report file {report_path} not found.")
        sys.exit(1)
        
    with open(report_path, "r", encoding="utf-8") as f:
        data = json.load(f)
        
    summary = data.get("summary", {})
    passed = summary.get("passed", 0)
    failed = summary.get("failed", 0)
    total = summary.get("total", 0)
    
    if total == 0:
        print("No tests were run.")
        sys.exit(1)
        
    pass_rate = (passed / total) * 100
    print(f"Total Tests: {total}")
    print(f"Passed: {passed}")
    print(f"Failed: {failed}")
    print(f"Pass Rate: {pass_rate:.2f}%")
    
    if pass_rate < 90.0:
        print("[FAILED] Pass rate is below the required 90% threshold.")
        sys.exit(1)
    else:
        print("[PASSED] Pass rate meets the 90% threshold.")

if __name__ == "__main__":
    main()
