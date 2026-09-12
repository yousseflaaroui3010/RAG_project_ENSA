import subprocess
import sys


def test_importing_the_web_app_does_not_load_sync_or_answer_engines():
    result = subprocess.run(
        [
            sys.executable,
            "-c",
            (
                "import sys; import app; "
                "assert 'conversion' not in sys.modules; "
                "assert 'agent.graph' not in sys.modules"
            ),
        ],
        check=False,
        capture_output=True,
        text=True,
        timeout=60,
    )

    assert result.returncode == 0, result.stderr
