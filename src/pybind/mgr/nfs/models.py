import ipaddress
from dataclasses import dataclass
from typing import Any, Optional, Union

from ceph.deployment.service_spec import PlacementSpec, SpecValidationError
from orchestrator.module import IngressType

from .exception import NFSInvalidOperation

PlacementInput = Optional[Union[str, dict[str, Any]]]
HostIPInput = Optional[list[dict[str, str]]]
NetworksInput = Optional[Union[str, list[str]]]


@dataclass(frozen=True)
class NFSClusterCreateRequest:
    cluster_id: str
    placement: Optional[str] = None
    ingress: Optional[bool] = None
    virtual_ip: Optional[str] = None
    ingress_mode: Optional[IngressType] = None
    ingress_placement: Optional[str] = None
    port: Optional[int] = None
    ip_addrs: Optional[dict[str, str]] = None
    monitoring_ip_addrs: Optional[dict[str, str]] = None
    monitoring_port: Optional[int] = None
    networks: Optional[list[str]] = None
    enable_nfsv3: bool = False
    enable_nfs_metrics: bool = False
    enable_rdma: bool = False
    rdma_port: Optional[int] = None

    @classmethod
    def from_api(
        cls,
        cluster_id: str,
        *,
        placement: PlacementInput = None,
        ingress: Optional[bool] = None,
        virtual_ip: Optional[str] = None,
        ingress_mode: Optional[Union[str, IngressType]] = None,
        ingress_placement: PlacementInput = None,
        port: Optional[int] = None,
        bind_addrs: HostIPInput = None,
        monitoring_addrs: HostIPInput = None,
        monitoring_port: Optional[int] = None,
        networks: NetworksInput = None,
        enable_nfsv3: bool = False,
        enable_nfs_metrics: bool = False,
        enable_rdma: bool = False,
        rdma_port: Optional[int] = None,
    ) -> 'NFSClusterCreateRequest':
        return cls(
            cluster_id=str(cluster_id),
            placement=_placement_to_str(placement, 'placement'),
            ingress=ingress,
            virtual_ip=virtual_ip,
            ingress_mode=_to_ingress_mode(ingress_mode),
            ingress_placement=_placement_to_str(ingress_placement, 'ingress_placement'),
            port=port,
            ip_addrs=_to_host_ip_map(bind_addrs, 'bind_addrs'),
            monitoring_ip_addrs=_to_host_ip_map(monitoring_addrs, 'monitoring_addrs'),
            monitoring_port=monitoring_port,
            networks=_to_networks(networks),
            enable_nfsv3=bool(enable_nfsv3),
            enable_nfs_metrics=bool(enable_nfs_metrics),
            enable_rdma=bool(enable_rdma),
            rdma_port=rdma_port,
        )


def _placement_to_str(placement: PlacementInput, field: str) -> Optional[str]:
    if placement is None or isinstance(placement, str):
        return placement or None
    if not isinstance(placement, dict):
        raise NFSInvalidOperation(f'{field} must be a string or an object')
    try:
        return PlacementSpec.from_json(placement).pretty_str() or None
    except SpecValidationError as e:
        raise NFSInvalidOperation(f'invalid {field}: {e}') from e


def _to_ingress_mode(mode: Optional[Union[str, IngressType]]) -> Optional[IngressType]:
    if mode is None or isinstance(mode, IngressType):
        return mode
    try:
        return IngressType(mode)
    except ValueError as e:
        valid = ', '.join(m.value for m in IngressType)
        raise NFSInvalidOperation(
            f"invalid ingress_mode '{mode}', expected one of: {valid}"
        ) from e


def _to_host_ip_map(entries: HostIPInput, field: str) -> Optional[dict[str, str]]:
    result: dict[str, str] = {}
    for entry in entries or []:
        hostname = (entry.get('hostname') or '').strip()
        ip = (entry.get('ip') or '').strip()
        if not hostname and not ip:
            continue
        if not hostname or not ip:
            raise NFSInvalidOperation(f'{field}: each entry needs both a hostname and an ip')
        try:
            ipaddress.ip_address(ip)
        except ValueError as e:
            raise NFSInvalidOperation(f"{field}: invalid IP address '{ip}'") from e
        if hostname in result:
            raise NFSInvalidOperation(f"{field}: host '{hostname}' is listed more than once")
        result[hostname] = ip
    return result or None


def _to_networks(networks: NetworksInput) -> Optional[list[str]]:
    if isinstance(networks, str):
        networks = [networks]
    result = [network.strip() for network in networks or [] if network and network.strip()]
    for network in result:
        try:
            ipaddress.ip_network(network)
        except ValueError as e:
            raise NFSInvalidOperation(f"invalid network '{network}': {e}") from e
    return result or None
