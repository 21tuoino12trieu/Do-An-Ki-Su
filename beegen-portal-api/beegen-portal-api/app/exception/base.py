class BeegenPortalApiError(Exception):
    pass

class PortalError(BeegenPortalApiError):
    pass

class ChunkerError(BeegenPortalApiError):
    pass