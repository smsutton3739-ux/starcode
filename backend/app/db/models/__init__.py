"""All ORM models.

Importing this package registers every mapper, which is what Alembic autogenerate and
`Base.metadata.create_all` need.
"""

from app.db.base import Base
from app.db.models.analysis import (
    AgentRun,
    Analysis,
    AnalysisStatus,
    Claim,
    ClaimType,
    Entity,
    EntityType,
    Reference,
    Report,
)
from app.db.models.content import (
    Collection,
    Document,
    Project,
    SearchHistory,
    Share,
    SourceKind,
    Tag,
    Upload,
    UploadStatus,
    analysis_tags,
    collection_analyses,
)
from app.db.models.knowledge import (
    EMBEDDING_DIM,
    AnalysisEmbedding,
    AstroEventType,
    AstronomicalEvent,
    CalendarSystem,
    Dataset,
    HistoricalSource,
    KnowledgeChunk,
    PromptTemplate,
    SourcePassage,
    SourceTradition,
)
from app.db.models.ops import (
    AstronomicalDatingUsage,
    AuditAction,
    AuditLog,
    Job,
    JobStatus,
    ProcessedStripeEvent,
)
from app.db.models.user import (
    Notification,
    OAuthIdentity,
    Role,
    SystemSetting,
    Tier,
    User,
    UserSetting,
)

__all__ = [
    "Base",
    "EMBEDDING_DIM",
    # user
    "User",
    "Role",
    "Tier",
    "ProcessedStripeEvent",
    "AstronomicalDatingUsage",
    "OAuthIdentity",
    "UserSetting",
    "SystemSetting",
    "Notification",
    # content
    "Project",
    "Upload",
    "UploadStatus",
    "Document",
    "SourceKind",
    "Tag",
    "Collection",
    "Share",
    "SearchHistory",
    "analysis_tags",
    "collection_analyses",
    # analysis
    "Analysis",
    "AnalysisStatus",
    "Claim",
    "ClaimType",
    "Entity",
    "EntityType",
    "Reference",
    "Report",
    "AgentRun",
    # knowledge
    "HistoricalSource",
    "SourcePassage",
    "SourceTradition",
    "AstronomicalEvent",
    "AstroEventType",
    "CalendarSystem",
    "KnowledgeChunk",
    "AnalysisEmbedding",
    "PromptTemplate",
    "Dataset",
    # ops
    "AuditLog",
    "AuditAction",
    "Job",
    "JobStatus",
]
