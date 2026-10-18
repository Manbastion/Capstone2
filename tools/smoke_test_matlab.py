"""Local acceptance test with a real MATLAB installation. Notifications opt-in.

python tools/smoke_test_matlab.py --matlab /Applications/MATLAB_R2025b.app/bin/matlab
Add --notify to send the completion alert through your configured channels.
"""
import argparse
from datetime import datetime
import importlib.util
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--matlab', default='matlab', help='Full MATLAB executable path, or matlab on PATH')
    parser.add_argument('--notify', action='store_true', help='Send through your enabled notification channels')
    parser.add_argument('--timeout', type=float, default=600)
    args = parser.parse_args(argv)
    spec = importlib.util.spec_from_file_location('habsim_smoke_runner', ROOT / 'grasshopper_components/matlab_runner.py')
    runner = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(runner)
    run_folder = ROOT / 'examples/notification_demo/runs'
    run_folder.mkdir(parents=True, exist_ok=True)
    script = ROOT / 'examples/notification_demo/workflow_demo.m'
    # Use an independent demo copy with known inputs, not the client's model.
    prepared = run_folder / 'notification_smoke_demo.m'
    content = script.read_text()
    import variable_transfer_v2 as backend
    prepared.write_text(content, encoding='utf-8')
    backend.transfer_data(str(ROOT / 'examples/notification_demo/workflow_inputs.py'), str(prepared), 'everything')
    try:
        job = runner.start_job(args.matlab, prepared, ['t', 'v', 's', 'final_displacement'],
                               run_folder, args.timeout, notify=args.notify)
    except (OSError, ValueError) as exc:
        print('Cannot start MATLAB: %s' % exc, file=sys.stderr)
        return 2
    print('MATLAB is running. Log: %s' % (job['directory'] / 'matlab.log'))
    try:
        while job['worker'].is_alive():
            job['worker'].join(timeout=.25)
    except KeyboardInterrupt:
        runner.cancel_job(job)
        job['worker'].join(timeout=15)
        return 130
    status = runner.job_status(job)
    proof = {'time': datetime.now().astimezone().isoformat(), 'platform': sys.platform,
             'python': sys.version.split()[0], 'state': status['state'], 'notification_requested': args.notify}
    passed = False
    if status['state'] == 'Succeeded':
        results = json.loads(Path(status['results_file']).read_text())
        value = results['final_displacement']
        value = value[0] if isinstance(value, list) else value
        passed = abs(value - 640) < 1e-9
        proof.update(final_displacement=value, expected=640, calculation_passed=passed)
        print('Final displacement: %s (expected 640)' % value)
    else:
        print('%s: %s' % (status['state'], status['message']), file=sys.stderr)
    receipt = job.get('notification')
    notification_passed = not args.notify
    if receipt is not None:
        proof['notification_attempt'] = receipt.wait(45)
        notification_passed = proof['notification_attempt']['status'] == 'submitted'
        print(json.dumps(proof['notification_attempt'], indent=2))
    proof['notification_submission_passed'] = notification_passed if args.notify else None
    evidence = job['directory'] / 'smoke_test_evidence.json'
    evidence.write_text(json.dumps(proof, indent=2), encoding='utf-8')
    print('Evidence: %s' % evidence)
    print('Confirm visually that the selected desktop/phone alert appeared; submission alone cannot prove receipt.')
    return 0 if passed and notification_passed else 1


if __name__ == '__main__':
    sys.exit(main())
