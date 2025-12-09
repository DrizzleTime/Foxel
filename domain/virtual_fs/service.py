from __future__ import annotations

from .common import VirtualFSCommonMixin
from .resolver import VirtualFSResolverMixin
from .listing import VirtualFSListingMixin
from .file_ops import VirtualFSFileOpsMixin
from .transfer import VirtualFSTransferMixin
from .processing import VirtualFSProcessingMixin
from .temp_link import VirtualFSTempLinkMixin
from .routes import VirtualFSRouteMixin


class VirtualFSService(
    VirtualFSRouteMixin,
    VirtualFSTempLinkMixin,
    VirtualFSProcessingMixin,
    VirtualFSTransferMixin,
    VirtualFSFileOpsMixin,
    VirtualFSListingMixin,
    VirtualFSResolverMixin,
    VirtualFSCommonMixin,
):
    pass
