
import logging
from collections import Counter
from enum import Enum
from typing import Any, Dict, List, Optional, TypedDict

import cherrypy
from orchestrator import OrchestratorError

from ..exceptions import DashboardException
from ..services._paginate import ListPaginator
from ..services.orchestrator import OrchClient

logger = logging.getLogger('services.hardware')


class Health(str, Enum):
    """
    API health strings. Members compare equal to (and serialize as) their
    string values. Lookup is case-insensitive, matching Redfish status.health
    values ("OK", "Warning", "Critical").
    """
    OK = 'OK'
    WARNING = 'Warning'
    CRITICAL = 'Critical'
    UNKNOWN = 'Unknown'

    @classmethod
    def _missing_(cls, value: object) -> Optional['Health']:
        if isinstance(value, str):
            for member in cls:
                if member.value.lower() == value.lower():
                    return member
        return None

    @classmethod
    def parse(cls, value: object) -> 'Health':
        """Like Health(value) but returns UNKNOWN for unrecognised values."""
        try:
            return cls(value)
        except ValueError:
            return cls.UNKNOWN

    @property
    def rank(self) -> int:
        """Severity ordering used to pick the worst health: higher is worse."""
        return _HEALTH_RANK[self]


_HEALTH_RANK = {
    Health.CRITICAL: 3,
    Health.WARNING: 2,
    Health.OK: 1,
    Health.UNKNOWN: 0,
}

STATUS_OK = Health.OK
STATUS_WARNING = Health.WARNING
STATUS_CRITICAL = Health.CRITICAL
STATUS_UNKNOWN = Health.UNKNOWN

# All category names match node-proxy keys directly in the API response.
_CATEGORIES = ['storage', 'processors', 'memory', 'network', 'power', 'fans', 'temperatures']


# ---------------------------------------------------------------------------
# Node proxy data model
#
# node-proxy daemons poll the BMC via Redfish and POST the assembled blob to
# cephadm every 5 minutes.  cephadm stores one blob per host in
# NodeProxyCache.data (in-memory + KV store).
#
# Access path: NodeProxyCache.data[hostname] -> HostReport
# ---------------------------------------------------------------------------

# pylint: disable=inherit-non-class
class ComponentStatus(TypedDict, total=False):
    health: str        # "OK", "Warning", "Critical"
    healthrollup: str
    state: str         # "Enabled", "Disabled", "UnavailableOffline", etc.


class Component(TypedDict, total=False):
    """Common fields shared by all category components.

    Each category (fans, storage, etc.) adds its own fields on top — e.g.
    fans add 'reading'/'reading_units', storage adds 'model'/'protocol' etc.
    """
    status: ComponentStatus
    name: str
    description: str
    reading: float
    reading_units: str
    physical_context: str
    model: str
    manufacturer: str
    serial_number: str
    capacity_bytes: int
    firmware_version: str
    slot: str
    protocol: str
    speed_mbps: int
    total_cores: int
    total_threads: int
    memory_device_type: str
    capacity_mi_b: int


# CategoryData: chassis_id -> component_id -> Component
_ComponentId = str
_ChassisId = str
_CategoryData = Dict[_ChassisId, Dict[_ComponentId, Component]]


class HardwareStatus(TypedDict, total=False):
    storage: _CategoryData
    processors: _CategoryData
    memory: _CategoryData
    network: _CategoryData
    power: _CategoryData
    fans: _CategoryData
    temperatures: _CategoryData
    fcm: _CategoryData


class FirmwareEntry(TypedDict, total=False):
    name: str
    description: str
    version: str
    release_date: str
    updateable: bool
    status: ComponentStatus


class HostReport(TypedDict, total=False):
    host: str
    sn: str
    status: HardwareStatus
    firmware: Dict[str, FirmwareEntry]


class CategorySummary(TypedDict):
    health: Health
    total: int
    ok: int
    warning: int
    critical: int


class HostSummary(TypedDict):
    hostname: str
    sn: str
    health: Health
    storage: CategorySummary
    processors: CategorySummary
    memory: CategorySummary
    network: CategorySummary
    power: CategorySummary
    fans: CategorySummary
    temperatures: CategorySummary
    firmware: Dict[str, str]

# pylint: enable=inherit-non-class


class HardwareService(object):

    @staticmethod
    def get_summary(categories: Optional[List[str]] = None,
                    hostname: Optional[List[str]] = None) -> Dict[str, Any]:
        total_count = {'total': 0, 'ok': 0, 'warn': 0, 'critical': 0}

        output: Dict[str, Any] = {
            'total': {
                'category': {},
                'total': {}
            },
            'host': {
                'flawed': 0
            }
        }

        def _get_health(component: Component) -> str:
            if not isinstance(component, dict):
                return STATUS_UNKNOWN
            status_val = component.get('status', {})
            if isinstance(status_val, dict):
                return status_val.get('health', STATUS_UNKNOWN)
            if isinstance(status_val, str):
                return status_val
            return STATUS_UNKNOWN

        def count_by_health(data: Dict[str, _CategoryData]) -> Dict[str, int]:
            counts = {'ok': 0, 'warn': 0, 'critical': 0}
            for node in data.values():
                for system in node.values():
                    for component in system.values():
                        health = _get_health(component)
                        if health == STATUS_OK:
                            counts['ok'] += 1
                        elif health == STATUS_WARNING:
                            counts['warn'] += 1
                        elif health == STATUS_CRITICAL:
                            counts['critical'] += 1
            return counts

        def count_total(data: Dict[str, _CategoryData]) -> int:
            return sum(
                len(component)
                for system in data.values()
                for component in system.values()
            )

        categories = HardwareService.validate_categories(categories)

        orch_hardware_instance = OrchClient.instance().hardware
        for category in categories:
            data = orch_hardware_instance.common(category, hostname)
            health_counts = count_by_health(data)
            category_total = {
                'total': count_total(data),
                'ok': health_counts['ok'],
                'warn': health_counts['warn'],
                'critical': health_counts['critical']
            }

            for host, systems in data.items():
                output['host'].setdefault(host, {'flawed': False})
                if not output['host'][host]['flawed']:
                    for system in systems.values():
                        if any(_get_health(comp) != STATUS_OK
                               for comp in system.values()):
                            output['host'][host]['flawed'] = True
                            break

            output['total']['category'].setdefault(category, {})
            output['total']['category'][category] = category_total

            total_count['total'] += category_total['total']
            total_count['ok'] += category_total['ok']
            total_count['warn'] += category_total['warn']
            total_count['critical'] += category_total['critical']

        output['total']['total'] = total_count

        output['host']['flawed'] = sum(
            1 for host in output['host']
            if host != 'flawed' and output['host'][host]['flawed']
        )

        return output

    @staticmethod
    def get_compression() -> Dict[str, Any]:
        """
        GET /api/hardware/compression -- cluster-wide FCM hardware compression stats.

        Aggregates FCM data from node-proxy cache across all hosts and drives.
        FCM data shape: status['fcm'][sys_id][device] = {
            compression_ratio, savings_bytes, phy_util_percent, log_util_percent, ...
        }

        compression_ratio, savings_bytes and efficiency_percent are gated on
        total physical used > 100 GiB to avoid misleading values from metadata
        on fresh/small clusters (mirrors Grafana dashboard behaviour).
        """
        MIN_PHY_UTIL_BYTES = 107_374_182_400  # 100 GiB

        try:
            fcm_data = OrchClient.instance().hardware.common('fcm')
        except OrchestratorError as e:
            logger.error("Failed to retrieve FCM data: %s", e)
            return {
                'fcm_drive_count': 0,
                'phy_util_percent': None,
                'log_util_percent': None,
                'savings_bytes': None,
                'compression_ratio': None,
                'efficiency_percent': None,
            }

        total_phy_util_bytes = 0
        total_log_util_bytes = 0
        total_phy_size_bytes = 0
        fcm_drive_count = 0

        for host_fcm in fcm_data.values():
            for sys_drives in host_fcm.values():
                if not isinstance(sys_drives, dict):
                    continue
                for drive in sys_drives.values():
                    if not isinstance(drive, dict):
                        continue
                    fcm_drive_count += 1
                    total_phy_util_bytes += drive.get('phy_util_bytes') or 0
                    total_log_util_bytes += drive.get('log_util_bytes') or 0
                    total_phy_size_bytes += drive.get('phy_size_bytes') or 0

        if fcm_drive_count == 0:
            return {
                'fcm_drive_count': 0,
                'phy_util_percent': None,
                'log_util_percent': None,
                'savings_bytes': None,
                'compression_ratio': None,
                'efficiency_percent': None,
            }

        phy_util_percent = round(
            (total_phy_util_bytes / total_phy_size_bytes) * 100, 2
        ) if total_phy_size_bytes else None

        # Gate ratio/savings/efficiency on minimum physical utilisation.
        if total_phy_util_bytes < MIN_PHY_UTIL_BYTES:
            return {
                'fcm_drive_count': fcm_drive_count,
                'phy_util_percent': phy_util_percent,
                'log_util_percent': None,
                'savings_bytes': None,
                'compression_ratio': None,
                'efficiency_percent': None,
            }

        compression_ratio = (
            round(total_log_util_bytes / total_phy_util_bytes, 2)
            if total_phy_util_bytes > 0 else None
        )
        savings_bytes = total_log_util_bytes - total_phy_util_bytes
        efficiency_percent = (
            round(100 * (1 - total_phy_util_bytes / total_log_util_bytes), 2)
            if total_log_util_bytes > 0 else None
        )
        log_util_percent = (
            round((total_log_util_bytes / total_phy_size_bytes) * 100, 2)
            if total_phy_size_bytes else None
        )

        return {
            'fcm_drive_count': fcm_drive_count,
            'phy_util_percent': phy_util_percent,
            'log_util_percent': log_util_percent,
            'savings_bytes': savings_bytes,
            'compression_ratio': compression_ratio,
            'efficiency_percent': efficiency_percent,
        }

    @staticmethod
    def get_hosts(offset: int = 0, limit: int = 5,
                  sort: str = '', search: str = '') -> List[HostSummary]:
        """
        GET /api/hardware/hosts — paginated list of hosts with hardware summary.

        Follows the RBD lazy-fetch pattern:
          1. Build cheap hostname refs for ALL hosts (no blobs loaded)
          2. ListPaginator sorts/searches/slices on refs — O(N log N) CPU, no I/O
          3. fullreport() called only for the current page — O(limit) blobs

        Total count is set in X-Total-Count response header (dashboard standard).
        TOCTOU: hosts removed between list_hosts() and fullreport() are skipped.
        """
        hardware = OrchClient.instance().hardware

        # Step 1: cheap refs — just hostnames, no blobs loaded.
        # Step 2: paginator sorts/searches/slices on refs.
        paginator = ListPaginator(
            offset, limit, sort, search,
            input_list=[{'hostname': h} for h in hardware.list_hosts()],
            searchable_params=['hostname'],
            sortable_params=['hostname'],
            default_sort='+hostname',
        )

        # Step 3: fullreport only for page items. It returns {hostname: blob},
        # so iterating .values() yields the single blob, or nothing if it is empty.
        hosts = [
            HardwareService._summarise_host(host_blob)
            for ref in paginator.list()
            for host_blob in hardware.fullreport(hostname=ref['hostname']).values()
            if host_blob
        ]

        # The paginator only knows the filtered count once list() is consumed.
        cherrypy.response.headers['X-Total-Count'] = paginator.get_count()
        return hosts

    @staticmethod
    def get_host_detail(hostname: str) -> Dict[str, Any]:
        """
        GET /api/hardware/hosts/{hostname} — full per-component detail for one host.
        """
        hardware = OrchClient.instance().hardware

        report = hardware.fullreport(hostname=hostname)
        host_data = report.get(hostname)
        if not host_data:
            raise DashboardException(
                msg=f"Host '{hostname}' has no node-proxy data",
                http_status_code=404,
                component='Hardware'
            )
        status = host_data.get('status', {})

        return {
            'hostname': host_data.get('host', hostname),
            'sn': host_data.get('sn', ''),

            # include_id=True: drive component_id (e.g. "disk.bay.8:...") is
            # the fallback identifier when physical_location data is absent.
            'storage': HardwareService._flatten_category(
                status.get('storage', {}),
                ['description', 'model', 'protocol', 'serial_number',
                 'capacity_bytes', 'firmware_version'],
                include_id=True
            ),

            'fans': HardwareService._flatten_category(
                status.get('fans', {}),
                ['name', 'physical_context', 'reading', 'reading_units']
            ),
            'temperatures': HardwareService._flatten_category(
                status.get('temperatures', {}),
                ['name', 'physical_context', 'reading', 'reading_units']
            ),
            # include_id=True: cpu.socket.1, cpu.socket.2 etc. identifies the physical socket.
            'processors': HardwareService._flatten_category(
                status.get('processors', {}),
                ['description', 'model', 'manufacturer', 'total_cores', 'total_threads',
                 'processor_type'],
                include_id=True
            ),
            # include_id=True: dimm.socket.a1 etc. identifies the physical DIMM slot.
            'memory': HardwareService._flatten_category(
                status.get('memory', {}),
                ['description', 'memory_device_type', 'capacity_mi_b'],
                include_id=True
            ),
            # include_id=True: oslogicalnetwork.2 etc. identifies the NIC interface.
            'network': HardwareService._flatten_category(
                status.get('network', {}),
                ['name', 'description', 'speed_mbps'],
                include_id=True
            ),
            'power': HardwareService._flatten_category(
                status.get('power', {}),
                ['name', 'model', 'manufacturer']
            ),
            'firmware': HardwareService._extract_firmware(
                host_data.get('firmware', host_data.get('firmwares', {}))
            ),
        }

    @staticmethod
    def validate_categories(categories: Optional[List[str]]) -> List[str]:
        categories_list = ['memory', 'storage', 'processors',
                           'network', 'power', 'fans', 'temperatures']

        if isinstance(categories, str):
            categories = [categories]
        elif categories is None:
            categories = categories_list
        elif not isinstance(categories, list):
            raise DashboardException(msg=f'{categories} is not a list',
                                     component='Hardware')
        if not all(item in categories_list for item in categories):
            raise DashboardException(
                msg=f'Invalid category, there is no {categories}',
                component='Hardware'
            )

        return categories

    # -----------------------------------------------------------------------
    # Private helpers
    # -----------------------------------------------------------------------

    @staticmethod
    def _get_component_health(component: Component) -> Health:
        """Extract the Redfish health string from a component dict, normalised to our constants.

        Examples:
            >>> HardwareService._get_component_health({})
            <Health.UNKNOWN: 'Unknown'>

            A status dictionary containing a known health value is mapped to our
            normalised status:
            >>> HardwareService._get_component_health({"status": {"health": "OK"}})
            <Health.OK: 'OK'>

            Health values are matched case-insensitively:
            >>> HardwareService._get_component_health({"status": {"health": "Warning"}})
            <Health.WARNING: 'Warning'>
            >>> HardwareService._get_component_health({"status": {"health": "CRITICAL"}})
            <Health.CRITICAL: 'Critical'>

            A status string is also accepted:
            >>> HardwareService._get_component_health({"status": "OK"})
            <Health.OK: 'OK'>

            Missing or unknown health values result in an unknown status:
            >>> HardwareService._get_component_health({"status": {}})
            <Health.UNKNOWN: 'Unknown'>
            >>> HardwareService._get_component_health({"status": {"health": "something-else"}})
            <Health.UNKNOWN: 'Unknown'>
            >>> HardwareService._get_component_health({"status": None})
            <Health.UNKNOWN: 'Unknown'>
        """
        try:
            status = component['status']
            if isinstance(status, dict):
                health = status.get('health', '')
            elif isinstance(status, str):
                health = status
            else:
                health = ''
            return Health.parse(health)
        except (KeyError, TypeError):
            return STATUS_UNKNOWN

    @staticmethod
    def _count_category(category_data: _CategoryData) -> CategorySummary:
        """
        Given one category's data for a single host
        (shape: sys_id -> component_id -> component_dict),
        return { health, total, ok, warning, critical }.

        health = worst across all components:  critical > warning > ok > unknown
        """
        counts = Counter(
            HardwareService._get_component_health(component)
            for sys_components in category_data.values()
            for component in sys_components.values()
            if isinstance(component, dict)
        )

        total = sum(counts.values())

        # Derive worst health: critical > warning > ok.
        if counts[STATUS_CRITICAL] > 0:
            worst = STATUS_CRITICAL
        elif counts[STATUS_WARNING] > 0:
            worst = STATUS_WARNING
        elif total > 0:
            worst = STATUS_OK
        else:
            worst = STATUS_UNKNOWN

        return {
            'health': worst,
            'total': total,
            'ok': counts[STATUS_OK],
            'warning': counts[STATUS_WARNING],
            'critical': counts[STATUS_CRITICAL],
        }

    @staticmethod
    def _extract_firmware(firmware_data: Dict[str, FirmwareEntry]) -> Dict[str, str]:
        """
        Flatten firmware inventory into { component_name: version }.
        The key in firmware_data is an opaque Redfish ID; we use the
        human-readable 'name' field instead.
        Skips entries with unknown/empty versions.
        """
        result: Dict[str, str] = {}
        for fw_info in firmware_data.values():
            if not isinstance(fw_info, dict):
                continue
            name = fw_info.get('name', '')
            version = fw_info.get('version', '')
            if name and version and version != 'unknown':
                result[name] = version
        return result

    @staticmethod
    def _flatten_category(category_data: _CategoryData, fields: List[str],
                          include_id: bool = False) -> List[Dict[str, Any]]:
        """
        Flatten a node-proxy category blob into a list of component dicts.

        Input shape: sys_id -> component_id -> { field: value, status: { health, state } }
        Output: [ { chassis_id, [id,] <fields...>, health, state }, ... ]

        :param category_data: one category's data for a single host
        :param fields:        list of field names to extract from each component
        :param include_id:    if True, include the Redfish component_id as 'id'
                              (useful for processors/memory where socket ID is meaningful)
        """
        result = []
        for chassis_id, components in category_data.items():
            for comp_id, component in components.items():
                if not isinstance(component, dict):
                    continue
                entry: Dict[str, Any] = {'chassis_id': chassis_id}
                if include_id:
                    entry['id'] = comp_id
                for field in fields:
                    if field in component:
                        entry[field] = component[field]

                # slot: Atollon sets a top-level 'slot' field; non-Atollon
                # hardware stores the bay as physical_location.partlocation.
                # locationordinalvalue. Try both so drives remain identifiable.
                if 'slot' not in entry:
                    loc = component.get('physical_location') or {}
                    entry['slot'] = (loc.get('partlocation') or {}).get(
                        'locationordinalvalue'
                    )

                status = component.get('status', {})
                entry['health'] = HardwareService._get_component_health(component)
                entry['state'] = status.get('state', '') if isinstance(status, dict) else ''
                result.append(entry)
        return result

    @staticmethod
    def _summarise_host(host_data: HostReport) -> HostSummary:
        """
        Build the per-host summary dict from a single host's fullreport blob.

        Shape of host_data (from NodeProxyCache):
            host_data['status'][category][sys_id][component_id] = { status, ... }
            host_data['firmware'][fw_id] = { name, version, ... }
            host_data['sn']   = serial number string
            host_data['host'] = hostname string

        """
        status = host_data.get('status', {})

        category_summaries: Dict[str, CategorySummary] = {}
        for cat in _CATEGORIES:
            cat_data = status.get(cat, {})
            category_summaries[cat] = HardwareService._count_category(cat_data)

        # Overall host health = worst health across all categories.
        worst = max(
            (s['health'] for s in category_summaries.values()),
            key=lambda h: Health.parse(h).rank,
            default=STATUS_UNKNOWN
        )

        firmware = HardwareService._extract_firmware(
            host_data.get('firmware', host_data.get('firmwares', {}))
        )

        return {
            'hostname': host_data.get('host', ''),
            'sn': host_data.get('sn', ''),
            'health': worst,
            'storage': category_summaries['storage'],
            'processors': category_summaries['processors'],
            'memory': category_summaries['memory'],
            'network': category_summaries['network'],
            'power': category_summaries['power'],
            'fans': category_summaries['fans'],
            'temperatures': category_summaries['temperatures'],
            'firmware': firmware,
        }
