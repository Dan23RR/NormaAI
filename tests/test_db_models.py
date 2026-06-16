"""Tests for database ORM models.

Validates model instantiation, default values, field types, and basic
constraints.  These are unit tests that do NOT require a running database;
they verify the Python-side ORM definitions only.
"""

import uuid
from datetime import date

from src.db.models import (
    Alert,
    Amendment,
    Assessment,
    Base,
    Client,
    Conversation,
    CrawlJob,
    Organization,
    Regulation,
    User,
)

# ------------------------------------------------------------------ #
#  Organization                                                       #
# ------------------------------------------------------------------ #


class TestOrganizationModel:
    def test_create_organization(self):
        org = Organization(
            id=uuid.uuid4(),
            name="Test Corp",
            slug="test-corp",
        )
        assert org.name == "Test Corp"
        assert org.slug == "test-corp"

    def test_default_plan_column_default_is_starter(self):
        """Column default for plan should be 'starter' (applied at INSERT time)."""
        col = Organization.__table__.columns["plan"]
        assert col.default.arg == "starter"

    def test_default_max_clients_column_default_is_5(self):
        col = Organization.__table__.columns["max_clients"]
        assert col.default.arg == 5

    def test_custom_plan_and_limits(self):
        org = Organization(
            id=uuid.uuid4(),
            name="Enterprise",
            slug="enterprise",
            plan="enterprise",
            max_clients=500,
        )
        assert org.plan == "enterprise"
        assert org.max_clients == 500

    def test_tablename(self):
        assert Organization.__tablename__ == "organizations"


# ------------------------------------------------------------------ #
#  User                                                               #
# ------------------------------------------------------------------ #


class TestUserModel:
    def test_create_user(self):
        org_id = uuid.uuid4()
        user = User(
            id=uuid.uuid4(),
            org_id=org_id,
            email="test@example.com",
            hashed_password="hashed",
            name="Test User",
            role="member",
        )
        assert user.email == "test@example.com"
        assert user.role == "member"
        assert user.name == "Test User"

    def test_user_default_role_column_default_is_member(self):
        """Column default for role should be 'member' (applied at INSERT time)."""
        col = User.__table__.columns["role"]
        assert col.default.arg == "member"

    def test_user_default_is_active_column_default(self):
        col = User.__table__.columns["is_active"]
        assert col.default.arg is True

    def test_admin_role(self):
        user = User(
            id=uuid.uuid4(),
            org_id=uuid.uuid4(),
            email="admin@test.com",
            hashed_password="hash",
            name="Admin",
            role="admin",
        )
        assert user.role == "admin"

    def test_tablename(self):
        assert User.__tablename__ == "users"


# ------------------------------------------------------------------ #
#  Client                                                             #
# ------------------------------------------------------------------ #


class TestClientModel:
    def test_create_client_basic(self):
        client = Client(
            id=uuid.uuid4(),
            org_id=uuid.uuid4(),
            name="Acme Srl",
        )
        assert client.name == "Acme Srl"

    def test_create_client_with_full_profile(self):
        client = Client(
            id=uuid.uuid4(),
            org_id=uuid.uuid4(),
            name="Acme Srl",
            sector="Manufacturing",
            employee_count=2500,
            revenue_eur=200_000_000,
            jurisdictions=["IT", "DE"],
            applicable_frameworks=["CSRD", "CSDDD"],
        )
        assert client.sector == "Manufacturing"
        assert client.employee_count == 2500
        assert client.revenue_eur == 200_000_000
        assert "IT" in client.jurisdictions
        assert "CSDDD" in client.applicable_frameworks

    def test_optional_fields_default_to_none(self):
        client = Client(
            id=uuid.uuid4(),
            org_id=uuid.uuid4(),
            name="Minimal",
        )
        assert client.sector is None
        assert client.employee_count is None
        assert client.revenue_eur is None

    def test_tablename(self):
        assert Client.__tablename__ == "clients"


# ------------------------------------------------------------------ #
#  Regulation                                                         #
# ------------------------------------------------------------------ #


class TestRegulationModel:
    def test_create_regulation(self):
        reg = Regulation(
            id=uuid.uuid4(),
            celex="32022L2464",
            title="Corporate Sustainability Reporting Directive",
            framework="CSRD",
            doc_type="directive",
        )
        assert reg.celex == "32022L2464"
        assert reg.framework == "CSRD"
        assert reg.doc_type == "directive"

    def test_default_is_in_force_column_default(self):
        """Column default for is_in_force should be True (applied at INSERT time)."""
        col = Regulation.__table__.columns["is_in_force"]
        assert col.default.arg is True

    def test_optional_dates(self):
        reg = Regulation(
            id=uuid.uuid4(),
            celex="32024R0002",
            title="Dated Regulation",
            framework="DORA",
            date_document=date(2024, 1, 15),
            date_in_force=date(2025, 1, 17),
        )
        assert reg.date_document == date(2024, 1, 15)
        assert reg.date_in_force == date(2025, 1, 17)

    def test_tablename(self):
        assert Regulation.__tablename__ == "regulations"


# ------------------------------------------------------------------ #
#  Amendment                                                          #
# ------------------------------------------------------------------ #


class TestAmendmentModel:
    def test_create_amendment(self):
        amendment = Amendment(
            id=uuid.uuid4(),
            amending_celex="32024L0001",
            amending_title="Omnibus I Simplification",
            amendment_date=date(2025, 2, 26),
            summary="Raised CSRD threshold to 1000 employees",
        )
        assert amendment.amending_celex == "32024L0001"
        assert amendment.summary is not None

    def test_amendment_without_original_regulation(self):
        """Amendments can exist without linking to an original."""
        amendment = Amendment(
            id=uuid.uuid4(),
            amending_celex="32024L0002",
        )
        assert amendment.original_regulation_id is None

    def test_tablename(self):
        assert Amendment.__tablename__ == "amendments"


# ------------------------------------------------------------------ #
#  Alert                                                              #
# ------------------------------------------------------------------ #


class TestAlertModel:
    def test_create_alert(self):
        alert = Alert(
            id=uuid.uuid4(),
            severity="HIGH",
            framework="CSRD",
            title="New CSRD deadline",
            description="Reporting deadline moved to Q1 2027",
        )
        assert alert.severity == "HIGH"
        assert alert.framework == "CSRD"

    def test_alert_column_defaults(self):
        """Column defaults for is_read/is_dismissed should be False."""
        assert Alert.__table__.columns["is_read"].default.arg is False
        assert Alert.__table__.columns["is_dismissed"].default.arg is False

    def test_tablename(self):
        assert Alert.__tablename__ == "alerts"


# ------------------------------------------------------------------ #
#  Assessment                                                         #
# ------------------------------------------------------------------ #


class TestAssessmentModel:
    def test_create_assessment_with_jsonb(self):
        assessment = Assessment(
            id=uuid.uuid4(),
            client_id=uuid.uuid4(),
            framework="CSRD",
            overall_score=42.5,
            gaps={"missing": ["ESRS E1", "ESRS S1"]},
            recommendations={"priority": "high", "actions": ["Hire ESG consultant"]},
        )
        assert assessment.overall_score == 42.5
        assert "missing" in assessment.gaps
        assert assessment.recommendations["priority"] == "high"

    def test_default_status_column_default_is_in_progress(self):
        """Column default for status should be 'in_progress'."""
        col = Assessment.__table__.columns["status"]
        assert col.default.arg == "in_progress"

    def test_tablename(self):
        assert Assessment.__tablename__ == "assessments"


# ------------------------------------------------------------------ #
#  Conversation                                                       #
# ------------------------------------------------------------------ #


class TestConversationModel:
    def test_create_conversation(self):
        conv = Conversation(
            id=uuid.uuid4(),
            user_id=uuid.uuid4(),
            messages=[
                {"role": "user", "content": "What is CSRD?"},
                {
                    "role": "assistant",
                    "content": "CSRD is the Corporate Sustainability Reporting Directive.",
                },
            ],
        )
        assert len(conv.messages) == 2
        assert conv.messages[0]["role"] == "user"

    def test_conversation_optional_client(self):
        conv = Conversation(
            id=uuid.uuid4(),
            user_id=uuid.uuid4(),
        )
        assert conv.client_id is None

    def test_tablename(self):
        assert Conversation.__tablename__ == "conversations"


# ------------------------------------------------------------------ #
#  CrawlJob                                                           #
# ------------------------------------------------------------------ #


class TestCrawlJobModel:
    def test_create_crawl_job(self):
        job = CrawlJob(
            id=uuid.uuid4(),
            job_type="full_crawl",
            status="pending",
        )
        assert job.job_type == "full_crawl"
        assert job.status == "pending"

    def test_crawl_job_column_defaults(self):
        """Column defaults: regulations_processed=0, amendments_found=0, status=pending."""
        cols = CrawlJob.__table__.columns
        assert cols["regulations_processed"].default.arg == 0
        assert cols["amendments_found"].default.arg == 0
        assert cols["status"].default.arg == "pending"

    def test_crawl_job_optional_fields(self):
        job = CrawlJob(
            id=uuid.uuid4(),
            job_type="amendment_check",
        )
        assert job.error_message is None
        assert job.started_at is None
        assert job.completed_at is None

    def test_tablename(self):
        assert CrawlJob.__tablename__ == "crawl_jobs"


# ------------------------------------------------------------------ #
#  Cross-model sanity checks                                          #
# ------------------------------------------------------------------ #


class TestBaseModel:
    def test_all_models_inherit_from_base(self):
        """All ORM models should inherit from our common Base."""
        models = [
            Organization,
            User,
            Client,
            Regulation,
            Amendment,
            Alert,
            Assessment,
            Conversation,
            CrawlJob,
        ]
        for model in models:
            assert issubclass(model, Base), f"{model.__name__} should inherit from Base"

    def test_all_models_have_id_column(self):
        """Every model should have an 'id' primary key."""
        models = [
            Organization,
            User,
            Client,
            Regulation,
            Amendment,
            Alert,
            Assessment,
            Conversation,
            CrawlJob,
        ]
        for model in models:
            columns = {c.name for c in model.__table__.columns}
            assert "id" in columns, f"{model.__name__} should have an 'id' column"
