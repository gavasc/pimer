import subprocess
import threading

_SOUND = "/usr/share/sounds/freedesktop/stereo/alarm-clock-elapsed.oga"
_FALLBACK = "/usr/share/sounds/freedesktop/stereo/complete.oga"


def fire(name: str) -> None:
    threading.Thread(target=_notify, args=(name,), daemon=True).start()
    threading.Thread(target=_sound, daemon=True).start()


def _notify(name: str) -> None:
    subprocess.run(
        ["notify-send", "-u", "critical", "-a", "pimer", "-i", "alarm", "pimer", name],
        check=False,
    )


def _sound() -> None:
    result = subprocess.run(
        ["ffplay", "-nodisp", "-autoexit", "-loglevel", "quiet",
         "-t", "4", "-af", "volume=1.5", _SOUND],
        check=False,
    )
    if result.returncode != 0:
        subprocess.run(["paplay", "--volume=65536", _FALLBACK], check=False)
