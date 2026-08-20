from enum import StrEnum


class LeadStatus(StrEnum):
    NEW = "NEW"
    ASSIGNED = "ASSIGNED"
    ATTEMPTED = "ATTEMPTED"
    CONTACTED = "CONTACTED"
    QUALIFIED = "QUALIFIED"
    DISQUALIFIED = "DISQUALIFIED"
    LOST = "LOST"
    CONVERTED = "CONVERTED"


class CustomerStatus(StrEnum):
    PROSPECT = "PROSPECT"
    ACTIVE = "ACTIVE"
    INACTIVE = "INACTIVE"
    BLOCKED = "BLOCKED"


class RecordStatus(StrEnum):
    DRAFT = "DRAFT"
    ACTIVE = "ACTIVE"
    INACTIVE = "INACTIVE"
    ARCHIVED = "ARCHIVED"


class DocumentStatus(StrEnum):
    PENDING = "PENDING"
    VERIFIED = "VERIFIED"
    REJECTED = "REJECTED"
    EXPIRED = "EXPIRED"


class ActivityType(StrEnum):
    CALL = "CALL"
    EMAIL = "EMAIL"
    MEETING = "MEETING"
    NOTE = "NOTE"
    STATUS_CHANGE = "STATUS_CHANGE"
    FOLLOW_UP = "FOLLOW_UP"


class ProjectStatus(StrEnum):
    PLANNING = "PLANNING"
    LAUNCHED = "LAUNCHED"
    UNDER_CONSTRUCTION = "UNDER_CONSTRUCTION"
    COMPLETED = "COMPLETED"
    ON_HOLD = "ON_HOLD"
    ARCHIVED = "ARCHIVED"


class UnitStatus(StrEnum):
    AVAILABLE = "AVAILABLE"
    SOFT_HOLD = "SOFT_HOLD"
    HARD_HOLD = "HARD_HOLD"
    BOOKING_INITIATED = "BOOKING_INITIATED"
    BOOKED = "BOOKED"
    SOLD = "SOLD"
    LEASED = "LEASED"
    BLOCKED = "BLOCKED"


class HoldStatus(StrEnum):
    ACTIVE = "ACTIVE"
    RELEASED = "RELEASED"
    EXPIRED = "EXPIRED"
    CONVERTED = "CONVERTED"


class VisitStatus(StrEnum):
    SCHEDULED = "SCHEDULED"
    CONFIRMED = "CONFIRMED"
    COMPLETED = "COMPLETED"
    CANCELLED = "CANCELLED"
    NO_SHOW = "NO_SHOW"


class QuotationStatus(StrEnum):
    DRAFT = "DRAFT"
    SENT = "SENT"
    ACCEPTED = "ACCEPTED"
    REJECTED = "REJECTED"
    EXPIRED = "EXPIRED"
    SUPERSEDED = "SUPERSEDED"


class BookingStatus(StrEnum):
    DRAFT = "DRAFT"
    DOCUMENTATION_PENDING = "DOCUMENTATION_PENDING"
    PAYMENT_PENDING = "PAYMENT_PENDING"
    SUBMITTED = "SUBMITTED"
    VERIFICATION = "VERIFICATION"
    APPROVAL = "APPROVAL"
    CONFIRMED = "CONFIRMED"
    CANCELLED = "CANCELLED"


class ApprovalStatus(StrEnum):
    PENDING = "PENDING"
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"
    CANCELLED = "CANCELLED"


class AgreementStatus(StrEnum):
    DRAFT = "DRAFT"
    ISSUED = "ISSUED"
    SIGNED = "SIGNED"
    REGISTERED = "REGISTERED"
    TERMINATED = "TERMINATED"


class PaymentStatus(StrEnum):
    PENDING = "PENDING"
    PROCESSING = "PROCESSING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    VOIDED = "VOIDED"
    REFUNDED = "REFUNDED"


class InstallmentStatus(StrEnum):
    SCHEDULED = "SCHEDULED"
    DUE = "DUE"
    PARTIALLY_PAID = "PARTIALLY_PAID"
    PAID = "PAID"
    OVERDUE = "OVERDUE"
    WAIVED = "WAIVED"


class LedgerEntryType(StrEnum):
    DEBIT = "DEBIT"
    CREDIT = "CREDIT"
    ADJUSTMENT = "ADJUSTMENT"


class WorkflowStatus(StrEnum):
    REQUESTED = "REQUESTED"
    UNDER_REVIEW = "UNDER_REVIEW"
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"
    COMPLETED = "COMPLETED"
    CANCELLED = "CANCELLED"


class PartnerStatus(StrEnum):
    PENDING = "PENDING"
    ACTIVE = "ACTIVE"
    SUSPENDED = "SUSPENDED"
    INACTIVE = "INACTIVE"


class CommissionStatus(StrEnum):
    PENDING = "PENDING"
    ELIGIBLE = "ELIGIBLE"
    APPROVED = "APPROVED"
    PAID = "PAID"
    REVERSED = "REVERSED"


class ProgressStatus(StrEnum):
    DRAFT = "DRAFT"
    PUBLISHED = "PUBLISHED"
    ARCHIVED = "ARCHIVED"


class PossessionStatus(StrEnum):
    PENDING = "PENDING"
    OFFERED = "OFFERED"
    SCHEDULED = "SCHEDULED"
    COMPLETED = "COMPLETED"
    DEFERRED = "DEFERRED"


class TenantStatus(StrEnum):
    ACTIVE = "ACTIVE"
    INACTIVE = "INACTIVE"
    BLACKLISTED = "BLACKLISTED"


class LeaseStatus(StrEnum):
    DRAFT = "DRAFT"
    ACTIVE = "ACTIVE"
    EXPIRED = "EXPIRED"
    TERMINATED = "TERMINATED"
    RENEWED = "RENEWED"


class InvoiceStatus(StrEnum):
    DRAFT = "DRAFT"
    ISSUED = "ISSUED"
    PARTIALLY_PAID = "PARTIALLY_PAID"
    PAID = "PAID"
    OVERDUE = "OVERDUE"
    VOIDED = "VOIDED"


class ServicePriority(StrEnum):
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    URGENT = "URGENT"


class ServiceStatus(StrEnum):
    OPEN = "OPEN"
    ASSIGNED = "ASSIGNED"
    IN_PROGRESS = "IN_PROGRESS"
    RESOLVED = "RESOLVED"
    CLOSED = "CLOSED"
    CANCELLED = "CANCELLED"


class NotificationChannel(StrEnum):
    IN_APP = "IN_APP"
    EMAIL = "EMAIL"
    SMS = "SMS"
    PUSH = "PUSH"


class NotificationStatus(StrEnum):
    QUEUED = "QUEUED"
    SENT = "SENT"
    DELIVERED = "DELIVERED"
    FAILED = "FAILED"
    READ = "READ"
