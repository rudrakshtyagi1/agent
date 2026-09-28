"""Run the bundled diagnostic suite against a running local API.

Usage: python scripts/run_evaluation_suite.py [--base-url http://127.0.0.1:8000]
Prints the complete persisted report as JSON for archival or inspection.
"""
import argparse
import json
import httpx


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--base-url', default='http://127.0.0.1:8000')
    args = parser.parse_args()
    response = httpx.post(args.base_url.rstrip('/') + '/api/v1/evaluation-suites/support-agent', timeout=60)
    response.raise_for_status()
    print(json.dumps(response.json(), indent=2))


if __name__ == '__main__':
    main()
