"""
Tests for the shared BaseSchema / ErrorBody in app/schemas/common.py.

Covers:
  - BaseSchema subclasses reject unknown fields (extra="forbid").
  - The _Base compatibility alias keeps the same behaviour.
  - ErrorBody matches the documented {"detail": str} contract.
  - Every public model in app.schemas.ml / app.schemas.simulation inherits
    BaseSchema, so the forbid rule cannot silently drift.
"""

import inspect

import pytest
from pydantic import BaseModel, ValidationError

from app.schemas import ml, simulation
from app.schemas.common import BaseSchema, ErrorBody, _Base


class _Sample(BaseSchema):
    name: str
    value: float = 0.0


class _LegacySample(_Base):
    name: str


def test_base_schema_accepts_declared_fields():
    obj = _Sample(name="a", value=1.5)
    assert obj.model_dump() == {"name": "a", "value": 1.5}


def test_base_schema_rejects_unknown_field():
    with pytest.raises(ValidationError) as exc_info:
        _Sample(name="a", unexpected=1)
    errors = exc_info.value.errors()
    assert [e["type"] for e in errors] == ["extra_forbidden"]
    assert errors[0]["loc"] == ("unexpected",)


def test_base_schema_rejects_unknown_field_via_model_validate():
    with pytest.raises(ValidationError):
        _Sample.model_validate({"name": "a", "unexpected": 1})


def test_base_schema_config_is_forbid():
    assert BaseSchema.model_config.get("extra") == "forbid"


def test_legacy_base_alias_rejects_unknown_field():
    assert issubclass(_Base, BaseSchema)
    with pytest.raises(ValidationError):
        _LegacySample(name="a", unexpected=1)


def test_error_body_shape():
    body = ErrorBody(detail="boom")
    assert body.model_dump() == {"detail": "boom"}


def test_error_body_requires_detail():
    with pytest.raises(ValidationError):
        ErrorBody()


def test_error_body_rejects_unknown_field():
    with pytest.raises(ValidationError):
        ErrorBody(detail="boom", code=500)


def _public_models(module):
    return [
        obj
        for name, obj in vars(module).items()
        if inspect.isclass(obj)
        and issubclass(obj, BaseModel)
        and obj.__module__ == module.__name__
    ]


@pytest.mark.parametrize(
    "model",
    _public_models(ml) + _public_models(simulation),
    ids=lambda m: f"{m.__module__}.{m.__name__}",
)
def test_shared_schema_models_inherit_base_schema(model):
    assert issubclass(model, BaseSchema)
    assert model.model_config.get("extra") == "forbid"
