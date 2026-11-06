"""No database transaction or candidate lock is held during model calls."""

import argparse
import logging
import time

from app.engine.validation import validate
from app.kernel.types import DomainError


def reasons_of(rejected):
    if isinstance(rejected, DomainError):
        return list(rejected.details.get("reasons") or [rejected.code])
    return ["schema_invalid"]


def generate(gateway, job, runs):
    """Call the model and return validated output, recording run metadata in runs.

    A5 takes three independent samples; a malformed sample counts as "invalid" and
    lowers confidence instead of failing the job. Every other component gets one
    bounded rewrite carrying only rule codes (never raw errors or rejected text);
    the rewrite must pass the same validation.
    """
    component, inputs = job["component"], job["inputs"]
    if component == "A5":
        samples = []
        for sample in range(3):
            try:
                result = gateway.call(component, inputs, job["id"], sample)
            except DomainError as exc:
                if exc.code != "AI_OUTPUT_REJECTED":
                    raise
                samples.append(None)
                runs.append({"kind": "invalid", "reasons": reasons_of(exc)})
                continue
            samples.append(result.pop("output"))
            runs.append(result)
        return validate(component, samples, inputs)
    reasons = None
    while True:
        try:
            result = gateway.call(component, inputs, job["id"], retry_reason=reasons)
            candidate = result.pop("output")
            runs.append({**result, "kind": "rewrite", "reasons": reasons} if reasons else result)
            return validate(component, [candidate], inputs)
        except (DomainError, ValueError, TypeError, KeyError) as rejected:
            if reasons is not None or (
                isinstance(rejected, DomainError) and rejected.code != "AI_OUTPUT_REJECTED"
            ):
                raise
            reasons = reasons_of(rejected)


def run_once(container, queue="batch"):
    with container.scope() as s:
        if container.settings.ai_worker_enabled:
            from app.engine.scheduler import schedule

            schedule(s, queue)
        job = s.engine.claim(queue)
    if job is None:
        return False
    runs, output, error = [], None, None
    try:
        output = generate(container.ai_gateway, job, runs)
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
