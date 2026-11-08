"""Deterministic model boundary ONLY for the disposable Playwright server."""


class BrowserAiGateway:
    def configured(self, component):
        # No A0 router here: natural-language commands use the keyword rules.
        return component != "A0"

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
        elif component == "A5":
            ref, value = next(iter(inputs["sources"].items()))
            quote = value[:20]
            output = {
                "items": [
                    {
                        "id": c["id"],
                        "verdict": "not_meet" if c["kind"] == "redflag" else "meet",
                        "evidence": [
                            {
                                "source": "profile" if ref.startswith("F:") else "resume",
                                "ref": ref,
                                "quote": quote,
                            }
                        ],
                        "note": "浏览器测试固定判断",
                    }
                    for c in inputs["criteria"]
                ],
                "questions": [],
                "self_confidence": 0.9,
            }
        elif component == "A7":
            ref = next(iter(inputs["sources"]))
            output = {
                "answer": "进度正常，主要停留在沟通阶段。",
                "data_refs": [ref],
                "suggestions": ["跟进沟通中的候选人"],
            }
        else:
            raise ValueError("This browser fixture covers A3, A5, A6 and A7 only")
        return {"output": output, "run_id": "browser-fixture", "tokens": 1, "elapsed_ms": 1}
