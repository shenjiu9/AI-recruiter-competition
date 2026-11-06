"""No database transaction or candidate lock is held during model calls."""

import argparse
import logging
import time

from app.engine.validation import validate
from app.kernel.types import DomainError


def run_once(container, queue="batch"):
    with container.scope() as s:
        if container.settings.ai_worker_enabled:
            from app.engine.scheduler import schedule

            schedule(s, queue)
        job = s.engine.claim(queue)
    if job is None:
        return False
    runs, samples, output, error = [], [], None, None
    try:
        for sample in range(3 if job["component"] == "A5" else 1):
            result = container.ai_gateway.call(job["component"], job["inputs"], job["id"], sample)
            samples.append(result.pop("output"))
            runs.append(result)
        output = validate(job["component"], samples, job["inputs"])
    except DomainError as exc:
        error = exc.code
    except (ValueError, TypeError, KeyError):
        error = "AI_OUTPUT_REJECTED"
    except Exception as exc:
        logging.getLogger("recruiter").warning("ai_provider_failure type=%s", type(exc).__name__)
        error = "AI_PROVIDER_UNAVAILABLE"
    with container.scope() as s:
        s.engine.finish(job["id"], job["lease"], output, runs, error)
    return True


def main():
    from app.bootstrap import build_container
    from app.platform.settings import Settings

    parser = argparse.ArgumentParser()
    parser.add_argument("--queue", choices=["batch", "realtime"], default="batch")
    parser.add_argument("--once", action="store_true")
    args = parser.parse_args()
    container = build_container(Settings())
    while True:
        processed = run_once(container, args.queue)
        if args.once:
            return
        if not processed:
            time.sleep(2)


if __name__ == "__main__":
    main()
