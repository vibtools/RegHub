class RegistryError(Exception):
    """Base class for expected registry failures."""


class NotFoundError(RegistryError):
    pass


class ConflictError(RegistryError):
    pass


class ValidationError(RegistryError):
    pass


class ExternalServiceError(RegistryError):
    pass


class AuthorizationError(RegistryError):
    pass


class FeatureDisabledError(RegistryError):
    pass
