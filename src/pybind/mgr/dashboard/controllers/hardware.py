
from typing import List, Optional

import cherrypy

from ..security import Scope
from ..services._paginate import ListPaginator
from ..services.hardware import HardwareService
from ..services.orchestrator import OrchClient
from . import APIDoc, APIRouter, EndpointDoc, Param, RESTController
from ._version import APIVersion


@APIRouter('/hardware', Scope.HOSTS)
@APIDoc("Hardware management API", "Hardware")
class Hardware(RESTController):

    @RESTController.Collection('GET', version=APIVersion.EXPERIMENTAL)
    @EndpointDoc("Retrieve a summary of the hardware health status")
    def summary(self, categories: Optional[List[str]] = None, hostname: Optional[List[str]] = None):
        """
        Get the health status of as many hardware categories, or all of them if none is given
        :param categories: The hardware type, all of them by default
        :param hostname: The host to retrieve from, all of them by default
        """
        return HardwareService.get_summary(categories, hostname)


@APIRouter('/hardware/compression')
@APIDoc("Hardware compression API", "Hardware")
class HardwareCompression(RESTController):

    @EndpointDoc("Retrieve cluster-wide FCM hardware compression statistics")
    def list(self):
        return HardwareService.get_compression()


@APIRouter('/hardware/hosts', Scope.HOSTS)
@APIDoc("Hardware hosts API", "Hardware")
class HardwareHosts(RESTController):

    @EndpointDoc(
        "List all hosts with hardware health summary, paginated.",
        parameters={
            'offset': Param(int, 'Offset into the host list (0-based)', True, 0),
            'limit': Param(int, 'Number of hosts to return (-1 for all)', True, 5),
            'sort': Param(str, 'Sort field, prefix with - for descending', True, ''),
            'search': Param(str, 'Search string to filter hosts by hostname', True, ''),
        }
    )
    def list(self, offset: int = 0, limit: int = 5, sort: str = '', search: str = ''):
        hardware = OrchClient.instance().hardware

        # Paginate cheap hostname refs first, then load blobs only for this page:
        # O(limit) blobs per request regardless of cluster size.
        paginator = ListPaginator(
            int(offset), int(limit), sort, search,
            input_list=[{'hostname': h} for h in hardware.list_hosts()],
            searchable_params=['hostname'],
            sortable_params=['hostname'],
            default_sort='+hostname',
        )
        hosts = [
            HardwareService.summarise_host(host_blob)
            for ref in paginator.list()
            if (host_blob := HardwareService.fetch_host_blob(hardware, ref['hostname']))
        ]

        # The paginator only knows the filtered count once list() is consumed.
        cherrypy.response.headers['X-Total-Count'] = paginator.get_count()
        return hosts

    @EndpointDoc(
        "Get full hardware detail for a single host, with per-component data for all categories.",
        parameters={
            'hostname': Param(str, 'The name of the host to retrieve hardware detail for', False),
        }
    )
    def get(self, hostname: str):
        return HardwareService.get_host_detail(hostname)
