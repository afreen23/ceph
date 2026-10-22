"""
Model definitions for the hardware API.

node-proxy daemons poll the BMC via Redfish and POST the assembled report to
cephadm every 5 minutes. cephadm keeps one report per host in
NodeProxyCache.data (in-memory + KV store).

Two layers live here:

* ``*Report`` TypedDicts describe the raw report as the orchestrator returns
  it (NodeProxyCache.data[hostname] -> HostReport).
* ``Component``, ``Category`` and ``HostHardware`` are the API models. Each is
  built from its part of the report with ``from_orch_report()``, exposes
  derived values (health, counts, ...) as properties and serializes with
  ``to_dict()``.
"""
from collections import Counter
from dataclasses import dataclass
from enum import Enum
from functools import cached_property
from typing import Any, Dict, List, Optional, TypedDict, cast


class Health(str, Enum):
    """
    API health strings. Members compare equal to (and serialize as) their
    string values. Lookup is case-insensitive, matching Redfish status.health
    values ("OK", "Warning", "Critical").

        >>> Health('critical')
        <Health.CRITICAL: 'Critical'>
        >>> Health.parse('something-else')
        <Health.UNKNOWN: 'Unknown'>
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


def _worst(healths: List[Health]) -> Health:
    return max(healths, key=lambda h: h.rank, default=Health.UNKNOWN)


# ---------------------------------------------------------------------------
# Raw node-proxy report, as returned by the orchestrator
# ---------------------------------------------------------------------------

# pylint: disable=inherit-non-class
class ComponentStatusReport(TypedDict, total=False):
    health: str        # "OK", "Warning", "Critical"
    healthrollup: str
    state: str         # "Enabled", "Disabled", "UnavailableOffline", etc.


class ComponentReport(TypedDict, total=False):
    """Fields a component may carry; which ones are present depends on the BMC.

    Each category (fans, storage, etc.) adds its own fields on top, e.g.
    fans add 'reading'/'reading_units', storage adds 'model'/'protocol' etc.
    """
    status: ComponentStatusReport
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
    slot: int
    protocol: str
    speed_mbps: int
    total_cores: int
    total_threads: int
    processor_type: str
    memory_device_type: str
    capacity_mi_b: int
    physical_location: Dict[str, Any]


# chassis_id -> component_id -> ComponentReport
CategoryReport = Dict[str, Dict[str, ComponentReport]]


class StatusReport(TypedDict, total=False):
    storage: CategoryReport
    processors: CategoryReport
    memory: CategoryReport
    network: CategoryReport
    power: CategoryReport
    fans: CategoryReport
    temperatures: CategoryReport
    fcm: CategoryReport


class FirmwareReport(TypedDict, total=False):
    name: str
    description: str
    version: str
    release_date: str
    updateable: bool
    status: ComponentStatusReport


class _HostReportRequired(TypedDict):
    # node-proxy always sends these (see BaseRedfishSystem.get_system()).
    host: str
    sn: str
    status: StatusReport


class HostReport(_HostReportRequired, total=False):
    firmware: Dict[str, FirmwareReport]
    firmwares: Dict[str, FirmwareReport]  # sent by older node-proxy versions

# pylint: enable=inherit-non-class


# ---------------------------------------------------------------------------
# API models
# ---------------------------------------------------------------------------

# Category -> component fields exposed by the API. Every component also gets
# id, chassis_id, health and state.
CATEGORY_FIELDS: Dict[str, List[str]] = {
    'storage': ['description', 'model', 'protocol', 'serial_number',
                'capacity_bytes', 'firmware_version', 'slot'],
    'processors': ['description', 'model', 'manufacturer', 'total_cores',
                   'total_threads', 'processor_type'],
    'memory': ['description', 'memory_device_type', 'capacity_mi_b'],
    'network': ['name', 'description', 'speed_mbps'],
    'power': ['name', 'model', 'manufacturer'],
    'fans': ['name', 'physical_context', 'reading', 'reading_units'],
    'temperatures': ['name', 'physical_context', 'reading', 'reading_units'],
}


@dataclass
class Component:
    """One hardware component: a fan, drive, DIMM, PSU, ..."""
    id: str
    chassis_id: str
    report: ComponentReport

    @classmethod
    def from_orch_report(cls, chassis_id: str, component_id: str,
                         report: ComponentReport) -> 'Component':
        return cls(id=component_id, chassis_id=chassis_id, report=report)

    @property
    def health(self) -> Health:
        try:
            return Health.parse(self.report['status']['health'])
        except KeyError:
            return Health.UNKNOWN
        except TypeError:
            # Older reports carry the health string itself as 'status'.
            return Health.parse(self.report['status'])

    @property
    def state(self) -> str:
        try:
            return self.report['status']['state']
        except (KeyError, TypeError):
            return ''

    @property
    def slot(self) -> Optional[int]:
        """Drive bay. Atollon sets 'slot'; other hardware only has physical_location."""
        try:
            return self.report['slot']
        except KeyError:
            pass
        try:
            return self.report['physical_location']['partlocation']['locationordinalvalue']
        except (KeyError, TypeError):
            return None

    def to_dict(self, fields: List[str]) -> Dict[str, Any]:
        report = cast(Dict[str, Any], self.report)
        data: Dict[str, Any] = {'id': self.id, 'chassis_id': self.chassis_id}
        data.update((field, report[field]) for field in fields if field in report)
        if 'slot' in fields:
            data['slot'] = self.slot
        data['health'] = self.health
        data['state'] = self.state
        return data


@dataclass
class Category:
    """All components of one category (fans, storage, ...) on a host."""
    name: str
    components: List[Component]

    @classmethod
    def from_orch_report(cls, name: str, report: CategoryReport) -> 'Category':
        return cls(name=name, components=[
            Component.from_orch_report(chassis_id, component_id, component)
            for chassis_id, components in report.items()
            for component_id, component in components.items()
            if isinstance(component, dict)
        ])

    @cached_property
    def _counts(self) -> 'Counter[Health]':
        return Counter(component.health for component in self.components)

    @property
    def health(self) -> Health:
        """Worst health across the components; UNKNOWN if there are none."""
        return _worst(list(self._counts))

    @property
    def total(self) -> int:
        return len(self.components)

    def to_dict(self) -> Dict[str, Any]:
        fields = CATEGORY_FIELDS[self.name]
        return {
            'health': self.health,
            'total': self.total,
            'ok': self._counts[Health.OK],
            'warning': self._counts[Health.WARNING],
            'critical': self._counts[Health.CRITICAL],
            'components': [component.to_dict(fields) for component in self.components],
        }


@dataclass
class HostHardware:
    """
    Hardware of one host, as returned by GET /api/hardware/hosts (one per host)
    and GET /api/hardware/hosts/{hostname}.
    """
    hostname: str
    sn: str
    status: Dict[str, Category]
    firmware: Dict[str, str]

    @classmethod
    def from_orch_report(cls, report: HostReport) -> 'HostHardware':
        # A category the BMC did not report is shown as empty.
        status = cast(Dict[str, CategoryReport], report['status'])
        return cls(
            hostname=report['host'],
            sn=report['sn'],
            status={
                name: Category.from_orch_report(name, status.get(name, {}))
                for name in CATEGORY_FIELDS
            },
            firmware=_firmware_versions(report.get('firmware', report.get('firmwares', {}))),
        )

    @property
    def health(self) -> Health:
        """Worst health across all categories."""
        return _worst([category.health for category in self.status.values()])

    def to_dict(self) -> Dict[str, Any]:
        return {
            'hostname': self.hostname,
            'sn': self.sn,
            'health': self.health,
            'status': {name: category.to_dict() for name, category in self.status.items()},
            'firmware': self.firmware,
        }


def _firmware_versions(report: Dict[str, FirmwareReport]) -> Dict[str, str]:
    """
    { component_name: version } from the firmware inventory. The report keys
    are opaque Redfish IDs, so the human-readable 'name' is used instead.
    Entries without a known version are skipped.
    """
    versions: Dict[str, str] = {}
    for entry in report.values():
        try:
            name, version = entry['name'], entry['version']
        except (KeyError, TypeError):
            continue
        if name and version and version != 'unknown':
            versions[name] = version
    return versions
