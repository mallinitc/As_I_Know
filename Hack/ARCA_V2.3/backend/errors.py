class ArcaBackendError(RuntimeError):
    """Base exception for sanitized API-layer error handling."""


class SnowflakeEvidenceError(ArcaBackendError):
    """Raised when required synthetic evidence cannot be loaded safely."""


class SnowflakeChangeNotFound(ArcaBackendError, LookupError):
    """Raised when a requested synthetic Snowflake change does not exist."""


class SnowflakeIdentityNotFound(ArcaBackendError, LookupError):
    """Raised when a Snowflake user identity cannot be resolved."""


class SnowflakeIdentityAmbiguous(ArcaBackendError):
    """Raised when an identity resolves to more than one user."""


class SnowflakeScenarioNotFound(ArcaBackendError, LookupError):
    """Raised when a post-implementation scenario does not exist."""


class AzureChangeNotFound(ArcaBackendError, LookupError):
    """Raised when a requested synthetic Azure change does not exist."""


class AzureScenarioNotFound(ArcaBackendError, LookupError):
    """Raised when a requested Azure demo scenario does not exist."""


class AzureEvidenceError(ArcaBackendError):
    """Raised when required synthetic Azure evidence cannot be loaded safely."""


class AzureIdentityNotFound(ArcaBackendError, LookupError):
    """Raised when an Azure principal ID or UPN cannot be resolved."""


class AzureIdentityAmbiguous(ArcaBackendError):
    """Raised when an Azure identity resolves to conflicting principals."""


class AwsEvidenceError(ArcaBackendError):
    """Raised when required synthetic AWS evidence cannot be loaded safely."""


class AwsChangeNotFound(ArcaBackendError, LookupError):
    """Raised when a requested synthetic AWS change does not exist."""

class AwsScenarioNotFound(ArcaBackendError, LookupError):
    """Raised when an AWS execution scenario does not exist."""

class AwsIdentityNotFound(ArcaBackendError, LookupError):
    """Raised when an AWS principal cannot be resolved."""
