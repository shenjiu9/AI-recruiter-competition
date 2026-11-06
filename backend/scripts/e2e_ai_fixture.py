"""Deterministic model boundary ONLY for the disposable Playwright server."""


class BrowserAiGateway:
    def configured(self, component):
        return True

    def call(self, component, inputs, action_id, sample=0, retry_reason=None):
        if component == "A3":
            value = inputs["sources"].get("F:skills", "")
            output = (
                {
                    "fields": {
                        "skills": {
                            "value": value,
                            "evidence": {"source": "profile", "ref": "F:skills", "quote": value},
                        }
                    }
                }
                if value
                else {"fields": {}}
            )
        elif component == "A6":
            ref, value = next(iter(inputs["sources"].items()))
            output = {
                "items": [
                    {
                        "id": "practice",
                        "notes": value,
                        "evidence": [{"source": "transcript", "ref": ref, "quote": value}],
                    }
                ]
            }
        else:
            raise ValueError("This browser fixture only covers extraction and interview notes")
        return {"output": output, "run_id": "browser-fixture", "tokens": 1, "elapsed_ms": 1}
