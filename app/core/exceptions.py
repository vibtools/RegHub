class RegistryError(Exception):
    """Base class for expected registry failures."""


class NotFoundError(RegistryError):
    pass


class ConflictError(RegistryError):
    pass


class DuplicateTemplateError(ConflictError):
    def __init__(
        self, message: str, *, template_id: object, template_slug: str, template_name: str
    ) -> None:
        super().__init__(message)
        self.template_id = template_id
        self.template_slug = template_slug
        self.template_name = template_name


class ValidationError(RegistryError):
    pass


class ExternalServiceError(RegistryError):
    pass


class AuthorizationError(RegistryError):
    pass


class PermissionDeniedError(AuthorizationError):
    pass


class FeatureDisabledError(RegistryError):
    pass
