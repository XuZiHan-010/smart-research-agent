"""Module 1: state + market_study_config checks."""

import sys
import typing

from backend.classes.config import DEPTH_CONFIGS, VALID_DEPTHS, VALID_OUTPUT_FORMATS
from backend.classes.market_study_config import GEOGRAPHY_OPTIONS, MARKET_THEMES, THEME_LABELS_ZH
from backend.classes.state import InputState, ResearchState, ThemeReport, job_status


def check(name: str, ok: bool, detail: str = "") -> bool:
    print(("PASS" if ok else "FAIL"), name, detail)
    return ok


def main() -> int:
    results = []
    results.append(check("seven default themes", len(MARKET_THEMES) == 7))
    results.append(check("theme keys unique", len({t["key"] for t in MARKET_THEMES}) == 7))
    results.append(check("theme labels complete", set(THEME_LABELS_ZH) == {t["key"] for t in MARKET_THEMES}))
    results.append(check("default geography cn", any(g["key"] == "cn" and g["checked"] for g in GEOGRAPHY_OPTIONS)))
    results.append(check("depth keys valid", set(VALID_DEPTHS) == set(DEPTH_CONFIGS)))
    results.append(check("word output supported", set(VALID_OUTPUT_FORMATS) == {"markdown", "pdf", "word"}))

    state_fields = set(typing.get_type_hints(ResearchState).keys())
    input_fields = set(typing.get_type_hints(InputState).keys())
    expected = {
        "research_domain", "selected_themes", "custom_themes", "geography",
        "time_range", "depth", "theme_depths", "output_format", "job_id",
        "theme_reports", "validation_report", "compacted_skeleton",
        "final_report_md", "citations_map", "events", "theme_depth_params",
    }
    results.append(check("InputState subset of ResearchState", input_fields <= state_fields))
    results.append(check("ResearchState required fields", expected <= state_fields, str(expected - state_fields)))
    results.append(check("ThemeReport has citations", "citations" in typing.get_type_hints(ThemeReport)))
    js = job_status["eval-module1"]
    results.append(check("job_status market key", "research_domain" in js and js["status"] == "pending"))
    return 0 if all(results) else 1


if __name__ == "__main__":
    sys.exit(main())
