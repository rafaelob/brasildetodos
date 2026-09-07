# SPDX-License-Identifier: AGPL-3.0-or-later
"""Verify both published releases together in a private, disposable installation."""
from __future__ import annotations
import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import platform
import tempfile

from install_national_catalog import install, accept_api


def exercise(health, education, *, health_selection, education_selection, output, static=None):
    output = Path(output)
    output.mkdir(parents=True, exist_ok=False)
    result = {'schema': 'bdt.national-acceptance.v1', 'status': 'started',
              'tested_revision': os.getenv('GITHUB_SHA', 'development'),
              'run_id': os.getenv('GITHUB_RUN_ID'), 'python': platform.python_version(),
              'public_deployment': False, 'fresh_collection': False,
              'existing_database_modified': False, 'browser_checked': False}
    stage = 'installation'
    try:
        with tempfile.TemporaryDirectory(prefix='bdt-national-acceptance-') as temporary:
            destination = Path(temporary) / 'application.db'
            result['installation'] = install(health, education, destination,
                health_selection=health_selection, education_selection=education_selection)
            stage = 'api'
            result['api'] = accept_api(destination, result['installation'])
            if static is not None:
                from browser_national_catalog import exercise_new_installation
                stage = 'browser'
                browser = exercise_new_installation(destination, result['installation'], static, output / 'browser')
                if browser['status'] != 'passed':
                    raise ValueError('national_browser_failed')
                result['browser_checked'] = True
                result['browser_combinations'] = len(browser['checks'])
            result['status'] = 'passed'
        return result
    except Exception as error:
        result.update(status='failed', failed_stage=stage, error_type=type(error).__name__)
        # No raw errors, local paths, database or document text in public receipts.
        raise
    finally:
        result['finished_at'] = datetime.now(timezone.utc).isoformat()
        (output / 'acceptance.json').write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n')


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--health', type=Path, required=True)
    parser.add_argument('--education', type=Path, required=True)
    parser.add_argument('--health-selection', type=Path, default=Path('data/releases/public-data-20260906-v1.json'))
    parser.add_argument('--education-selection', type=Path, default=Path('data/releases/education-2025-20260907-v1.json'))
    parser.add_argument('--output', type=Path, default=Path('test-results/national-acceptance'))
    parser.add_argument('--static', type=Path)
    args = parser.parse_args(argv)
    result = exercise(args.health, args.education, health_selection=args.health_selection,
                      education_selection=args.education_selection, output=args.output, static=args.static)
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
