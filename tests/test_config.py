"""Settings safety checks: CORS parsing and production guards."""

import pytest
from pydantic import ValidationError

from app.config import DEFAULT_JWT_SECRET, Settings

STRONG_SECRET = "x" * 40


def make(**kwargs) -> Settings:
    return Settings(_env_file=None, **kwargs)


def test_cors_origins_parsed_and_trimmed():
    s = make(CORS_ORIGINS=" https://a.com/ , https://b.com ,")
    assert s.cors_origins_list == ["https://a.com", "https://b.com"]


def test_cors_wildcard_collapses_to_star():
    assert make(CORS_ORIGINS="https://a.com,*").cors_origins_list == ["*"]


def test_development_allows_defaults():
    s = make(ENVIRONMENT="development", CORS_ORIGINS="*")
    assert s.JWT_SECRET == DEFAULT_JWT_SECRET
    assert not s.is_production


def test_unknown_env_vars_are_ignored():
    assert make(SOME_UNRELATED_SETTING="1").APP_NAME


@pytest.mark.parametrize("secret", [DEFAULT_JWT_SECRET, "too-short"])
def test_production_rejects_weak_jwt_secret(secret):
    with pytest.raises(ValidationError, match="JWT_SECRET"):
        make(ENVIRONMENT="production", JWT_SECRET=secret, CORS_ORIGINS="https://app.example.com")


@pytest.mark.parametrize("origins", ["*", "", "https://a.com,*"])
def test_production_rejects_open_cors(origins):
    with pytest.raises(ValidationError, match="CORS_ORIGINS"):
        make(ENVIRONMENT="production", JWT_SECRET=STRONG_SECRET, CORS_ORIGINS=origins)


def test_production_accepts_safe_config():
    s = make(
        ENVIRONMENT="Production",
        JWT_SECRET=STRONG_SECRET,
        CORS_ORIGINS="https://app.example.com",
    )
    assert s.is_production
    assert s.cors_origins_list == ["https://app.example.com"]
