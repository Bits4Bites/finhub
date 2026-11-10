import pytest

from app import config


@pytest.mark.parametrize(
    ("raw_models", "expected"),
    [
        (" model-a, model-b, model-a, , ", {"model-a", "model-b"}),
        ("", set()),
    ],
)
def test_llm_models_decode_csv_from_dotenv(tmp_path, monkeypatch, raw_models, expected):
    monkeypatch.delenv("MODELS", raising=False)
    env_file = tmp_path.joinpath("ai_vendors.env")
    env_file.write_text(f'MODELS="{raw_models}"\n', encoding="utf-8")

    settings = config.LLMConfig(_env_file=env_file)

    assert settings.models == expected


def test_llm_vendors_decode_nested_csv_and_empty_models(tmp_path, monkeypatch):
    monkeypatch.delenv("MODELS", raising=False)
    monkeypatch.delenv("FINHUB_LLM", raising=False)
    env_file = tmp_path.joinpath("ai_vendors.env")
    env_file.write_text(
        'FINHUB_LLM__TEST__PRIMARY__MODELS=" model-a, model-b, model-a, , "\nFINHUB_LLM__TEST__DISABLED__MODELS=""\n',
        encoding="utf-8",
    )

    settings = config.LLMVendorSettings(_env_file=env_file)

    assert settings.vendors["test"]["primary"].models == {"model-a", "model-b"}
    assert settings.vendors["test"]["disabled"].models == set()


@pytest.mark.parametrize(
    ("raw_mode", "expected"),
    [
        (None, "Standard"),
        ("Economy", "Economy"),
        ("economy", "Economy"),
        ("EcOnOmY", "Economy"),
        (" ECONOMY ", "Economy"),
        ("Standard", "Standard"),
        ("unsupported-mode", "Standard"),
        ("", "Standard"),
        ("   ", "Standard"),
    ],
)
def test_llm_tokenomics_mode_normalizes_dotenv_values(tmp_path, monkeypatch, raw_mode, expected):
    monkeypatch.delenv("FINHUB_LLM_TOKENOMICS_MODE", raising=False)
    env_file = tmp_path.joinpath("ai_tasks.env")
    env_file.write_text(
        "" if raw_mode is None else f'FINHUB_LLM_TOKENOMICS_MODE="{raw_mode}"\n',
        encoding="utf-8",
    )

    settings = config.LLMTaskSettings(_env_file=env_file)

    assert settings.tokenomics_mode == expected


@pytest.mark.parametrize(
    ("file_mode", "env_mode", "expected"),
    [
        ("Standard", "economy", "Economy"),
        ("Economy", "unsupported-mode", "Standard"),
    ],
)
def test_llm_tokenomics_mode_environment_overrides_dotenv(tmp_path, monkeypatch, file_mode, env_mode, expected):
    env_file = tmp_path.joinpath("ai_tasks.env")
    env_file.write_text(f'FINHUB_LLM_TOKENOMICS_MODE="{file_mode}"\n', encoding="utf-8")
    monkeypatch.setenv("FINHUB_LLM_TOKENOMICS_MODE", env_mode)

    settings = config.LLMTaskSettings(_env_file=env_file)

    assert settings.tokenomics_mode == expected
