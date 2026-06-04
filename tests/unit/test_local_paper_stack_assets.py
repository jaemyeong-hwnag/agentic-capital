"""Static checks for the independent local paper stack runner and skill."""

from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


def test_local_paper_stack_defaults_to_independent_direct_mode() -> None:
    script = (ROOT / "scripts" / "run_local_paper_stack.sh").read_text()

    assert 'LOCAL_LLM_RUNTIME_MODE="${LOCAL_LLM_RUNTIME_MODE:-direct}"' in script
    assert 'AGENTIC_CAPITAL_MODEL_CACHE="${AGENTIC_CAPITAL_MODEL_CACHE:-$HOME/.cache/agentic-capital/models}"' in script
    assert 'LOCAL_FINANCE_DECISION_BASE_URL="$finance_decision_base_url"' in script
    assert 'finance_decision_base_url="http://$HOST:18183/v1"' in script
    assert 'LOCAL_PSYCHOLOGY_BASE_URL="$psychology_base_url"' in script
    assert 'psychology_base_url="http://$HOST:18080/v1"' in script


def test_local_paper_stack_maps_project_huggingface_token() -> None:
    script = (ROOT / "scripts" / "run_local_paper_stack.sh").read_text()

    assert 'load_env_file "$PROJECT_ROOT/.env"' in script
    assert 'export HF_TOKEN="${HF_TOKEN:-${HUGGINGFACE_TOKEN:-}}"' in script
    assert "raiss123/finance_decision_model-qwen3-4b-instruct-2507" in script


def test_local_paper_stack_skill_is_registered() -> None:
    skill = ROOT / ".agents" / "skills" / "source-command-local-paper-stack" / "SKILL.md"
    text = skill.read_text()

    assert 'name: "source-command-local-paper-stack"' in text
    assert "LOCAL_LLM_RUNTIME_MODE=direct" in text
    assert "./scripts/run_local_paper_stack.sh start" in text
    assert "KIS_IS_PAPER=true" in text
