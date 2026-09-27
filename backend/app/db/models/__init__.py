"""ORM model registry.

Importing this package causes all SQLAlchemy models to register themselves
in Base.metadata.  This is required before create_all() or Alembic autogenerate.
"""

from app.db.models.agent import AgentModel
from app.db.models.evaluation import EvaluationModel
from app.db.models.experiment import ExperimentModel
from app.db.models.failure import FailureModel
from app.db.models.run import RunModel
from app.db.models.test_case import TestCaseModel
from app.db.models.trace import TraceSpanModel

__all__ = [
    "AgentModel",
    "TestCaseModel",
    "RunModel",
    "TraceSpanModel",
    "EvaluationModel",
    "FailureModel",
    "ExperimentModel",
]
