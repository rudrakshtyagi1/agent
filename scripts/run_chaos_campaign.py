"""Run a local paired chaos campaign and print the complete saved JSON report."""
import argparse
import json
import httpx


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--base-url', default='http://127.0.0.1:8000')
    parser.add_argument('--seed', type=int, default=42)
    parser.add_argument('--probability', type=float, default=1.0)
    parser.add_argument('--fault-attempts', type=int, default=1)
    parser.add_argument('--max-attempts', type=int, default=2)
    args = parser.parse_args()
    response = httpx.post(args.base_url.rstrip('/') + '/api/v1/chaos/campaigns',
                          json={'seed': args.seed, 'probability': args.probability,
                                'fail_first_attempts': args.fault_attempts,
                                'retry': {'max_attempts': args.max_attempts}}, timeout=120)
    response.raise_for_status()
    print(json.dumps(response.json(), indent=2))


if __name__ == '__main__':
    main()
