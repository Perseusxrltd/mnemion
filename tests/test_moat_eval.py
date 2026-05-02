def test_moat_eval_reports_all_modes_and_suites(tmp_path):
    from mnemion.moat_eval import run_moat_eval

    result = run_moat_eval(suite="all", kg_path=str(tmp_path / "kg.sqlite3"))

    assert result["suite"] == "all"
    assert set(result["modes"]) == {
        "raw_vector",
        "hybrid_rrf",
        "trust_kg",
        "cognitive_reconstruction",
    }
    assert {"struct", "causal", "forgetting", "security"}.issubset(result["scores"])


def test_moat_eval_rejects_unknown_suite(tmp_path):
    from mnemion.moat_eval import run_moat_eval

    result = run_moat_eval(suite="unknown", kg_path=str(tmp_path / "kg.sqlite3"))

    assert "error" in result


def test_moat_eval_runs_structural_topic_tunnel_case(tmp_path):
    from mnemion.moat_eval import run_moat_eval

    result = run_moat_eval(suite="struct", kg_path=str(tmp_path / "kg.sqlite3"))

    assert result["case_counts"]["struct"] >= 1
    assert result["scores"]["struct"]["cognitive_reconstruction"] > 0.0
    assert result["cases"]["struct"][0]["passed"]["cognitive_reconstruction"] is True


def test_moat_eval_runs_security_guard_case(tmp_path):
    from mnemion.moat_eval import run_moat_eval

    result = run_moat_eval(suite="security", kg_path=str(tmp_path / "kg.sqlite3"))

    assert result["scores"]["security"]["trust_kg"] == 1.0
    assert result["cases"]["security"][0]["findings"]


def test_moat_eval_response_schema_is_stable(tmp_path):
    from mnemion.moat_eval import run_moat_eval

    result = run_moat_eval(suite="all", kg_path=str(tmp_path / "kg.sqlite3"))

    assert set(result) == {"suite", "kg_path", "modes", "scores", "case_counts", "cases"}
    assert result["suite"] == "all"
    assert result["modes"] == [
        "raw_vector",
        "hybrid_rrf",
        "trust_kg",
        "cognitive_reconstruction",
    ]
    for suite_name, cases in result["cases"].items():
        assert result["case_counts"][suite_name] == len(cases)
        for mode in result["modes"]:
            assert isinstance(result["scores"][suite_name][mode], float)
        for case in cases:
            assert {"name", "passed"}.issubset(case)
            assert set(case["passed"]) == set(result["modes"])


def test_moat_benchmark_summary_counts_modes():
    from benchmarks.moat_benchmark import summarize

    result = {
        "modes": ["trust_kg", "cognitive_reconstruction"],
        "cases": {
            "forgetting": [
                {"passed": {"trust_kg": True, "cognitive_reconstruction": True}},
                {"passed": {"trust_kg": False, "cognitive_reconstruction": True}},
            ]
        },
    }

    summary = summarize(result)

    assert summary["mode_totals"]["trust_kg"] == {"passed": 1, "total": 2, "score": 0.5}
    assert summary["mode_totals"]["cognitive_reconstruction"] == {
        "passed": 2,
        "total": 2,
        "score": 1.0,
    }
