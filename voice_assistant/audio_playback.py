import subprocess
import threading


def get_duration(filepath: str) -> float:
    result = subprocess.run(
        ["afinfo", filepath],
        capture_output=True,
        text=True,
    )
    for line in result.stdout.splitlines():
        if "estimated duration" in line.lower():
            return float(line.split(":")[-1].strip().split()[0])
    return 2.0


def play_audio(filepath: str, on_start=None, on_done=None):
    def _play():
        import time; time.sleep(0.5)
        duration = get_duration(filepath)
        if on_start:
            on_start(duration)
        subprocess.run(["afplay", filepath], capture_output=True)
        if on_done:
            on_done()

    t = threading.Thread(target=_play, daemon=True)
    t.start()
