"""Run the blinded nine-fixture diagnosis regression audit against the local API."""
import argparse
import json
import httpx


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--base-url',default='http://127.0.0.1:8000')
    args=parser.parse_args()
    response=httpx.post(args.base_url.rstrip('/')+'/api/v1/failures/benchmark',timeout=120)
    response.raise_for_status()
    report=response.json()
    print(json.dumps(report,indent=2))
    if report['correct'] != report['total']:
        raise SystemExit(1)


if __name__=='__main__':
    main()
