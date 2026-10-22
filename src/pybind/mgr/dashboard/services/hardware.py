import logging
from collections import Counter
from typing import Dict, Iterable, List, Optional, Union

from orchestrator import OrchestratorError

from ..exceptions import DashboardException
from ..model.hardware import Category, Component, CompressionStats, \
    HardwareSummary, Health, HealthCounts, HostFlawed, SummaryTotals
from ..services.orchestrator import OrchClient

logger = logging.getLogger('services.hardware')


class HardwareService(object):

    @staticmethod
    def get_summary(categories: Optional[List[str]] = None,
                    hostname: Optional[List[str]] = None) -> HardwareSummary:
        """
        Health counts per category across the given hosts (all by default),
        and which hosts have any component that is not OK.
        """
        hardware = OrchClient.instance().hardware
        per_category: Dict[str, HealthCounts] = {}
        host_flawed: Dict[str, bool] = {}
        for name in HardwareService.validate_categories(categories):
            components: List[Component] = []
            for host, report in hardware.common(name, hostname).items():
                category = Category.from_orch_report(name, report)
                components.extend(category.components)
                host_flawed[host] = host_flawed.get(host, False) or any(
                    component.health != Health.OK for component in category.components)
            per_category[name] = _health_counts(components)

        hosts: Dict[str, Union[HostFlawed, int]] = {
            host: HostFlawed(flawed=flawed) for host, flawed in host_flawed.items()}
        hosts['flawed'] = sum(host_flawed.values())
        return HardwareSummary(
            total=SummaryTotals(category=per_category,
                                total=_sum_health_counts(per_category.values())),
            host=hosts,
        )

    @staticmethod
    def get_compression() -> CompressionStats:
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
            fcm_data = OrchClient.instance().hardware.fcm()
        except OrchestratorError as e:
            logger.error("Failed to retrieve FCM data: %s", e)
            return CompressionStats(
                fcm_drive_count=0,
                phy_util_percent=None,
                log_util_percent=None,
                savings_bytes=None,
                compression_ratio=None,
                efficiency_percent=None,
            )

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
            return CompressionStats(
                fcm_drive_count=0,
                phy_util_percent=None,
                log_util_percent=None,
                savings_bytes=None,
                compression_ratio=None,
                efficiency_percent=None,
            )

        phy_util_percent = round(
            (total_phy_util_bytes / total_phy_size_bytes) * 100, 2
        ) if total_phy_size_bytes else None

        # Gate ratio/savings/efficiency on minimum physical utilisation.
        if total_phy_util_bytes < MIN_PHY_UTIL_BYTES:
            return CompressionStats(
                fcm_drive_count=fcm_drive_count,
                phy_util_percent=phy_util_percent,
                log_util_percent=None,
                savings_bytes=None,
                compression_ratio=None,
                efficiency_percent=None,
            )

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

        return CompressionStats(
            fcm_drive_count=fcm_drive_count,
            phy_util_percent=phy_util_percent,
            log_util_percent=log_util_percent,
            savings_bytes=savings_bytes,
            compression_ratio=compression_ratio,
            efficiency_percent=efficiency_percent,
        )

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


def _health_counts(components: List[Component]) -> HealthCounts:
    counts = Counter(component.health for component in components)
    return HealthCounts(total=len(components), ok=counts[Health.OK],
                        warn=counts[Health.WARNING], critical=counts[Health.CRITICAL])


def _sum_health_counts(counts: Iterable[HealthCounts]) -> HealthCounts:
    total = HealthCounts(total=0, ok=0, warn=0, critical=0)
    for c in counts:
        total = HealthCounts(total=total['total'] + c['total'], ok=total['ok'] + c['ok'],
                             warn=total['warn'] + c['warn'],
                             critical=total['critical'] + c['critical'])
    return total
