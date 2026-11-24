import eval as harness


def test_offline_eval_all_pass(capsys):
    assert harness.main(["--no-save"]) == 0
    out = capsys.readouterr().out
    assert "Overall: 14/14 passed" in out and "Average confidence" in out


def test_check_reports_mismatch():
    from schedule_agent import ImportResult
    case = harness.Case("x", "t", [], added=1, reject_has="conflict")
    ok, note = harness.check(case, ImportResult())
    assert not ok and "expected 1 added" in note and "conflict" in note


def test_demo_runs_offline(capsys, monkeypatch):
    import guardrails
    import demo
    monkeypatch.setattr(guardrails, "_sleep", lambda s: None)
    assert demo.main([]) == 0
    out = capsys.readouterr().out
    assert "unknown pet 'Rex'" in out and "fallback=True" in out and "Riptide" in out


def test_retrieval_comparison_shows_improvement():
    rows, base, rag = harness.run_retrieval_comparison()
    assert len(rows) == 5 and rag == 25 and base < rag
