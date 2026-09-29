"""Offline CI gate. Exit 0: pass, 1: rejected, 2: execution error."""
import argparse
import asyncio
import json
import tempfile
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'backend'))
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker
from app.db.session import Base
from app.db import models
from app.schemas.regression import ComparisonRequest, GatePolicy
from app.reliability.version_compare import run_comparison

async def main(args):
    request = ComparisonRequest(baseline_version=args.baseline_version, candidate_version=args.candidate_version,
                                gate=GatePolicy(max_regressions=args.max_regressions,
                                                min_task_success_rate=args.min_success_rate))
    with tempfile.TemporaryDirectory(prefix='agentguard-release-') as directory:
        engine = create_async_engine(f'sqlite+aiosqlite:///{directory}/gate.db')
        try:
            async with engine.begin() as connection:
                await connection.run_sync(Base.metadata.create_all)
            async with async_sessionmaker(engine, expire_on_commit=False)() as db:
                report = await run_comparison(db, request)
                await db.commit()
            serialized = json.dumps(report, indent=2)
            if args.output:
                Path(args.output).write_text(serialized + '\n')
            print(serialized)
            return 0 if report['gate']['passed'] else 1
        finally:
            await engine.dispose()

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--baseline-version', default='1.0.0')
    parser.add_argument('--candidate-version', default='1.1.0')
    parser.add_argument('--max-regressions', type=int, default=0)
    parser.add_argument('--min-success-rate', type=float, default=1)
    parser.add_argument('--output')
    try:
        sys.exit(asyncio.run(main(parser.parse_args())))
    except Exception as error:
        print(f'Release gate error: {error}', file=sys.stderr)
        sys.exit(2)
