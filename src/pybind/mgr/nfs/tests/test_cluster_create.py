import dataclasses
import inspect
from unittest import mock
from unittest.mock import MagicMock

import pytest

from ceph.deployment.service_spec import PlacementSpec
from nfs.cluster import NFSCluster
from nfs.exception import NFSInvalidOperation
from nfs.models import NFSClusterCreateRequest
from orchestrator.module import IngressType


class TestNFSClusterCreateRequest:
    def test_placement_dict_is_parsed_by_placement_spec(self):
        placement = {'count': 2, 'hosts': ['host1', 'host2']}
        request = NFSClusterCreateRequest.from_api('mynfs', placement=placement)
        assert request.placement == 'host1;host2;count:2'
        assert PlacementSpec.from_string(request.placement) == PlacementSpec.from_json(placement)

    def test_host_pattern_is_kept(self):
        placement = {'count': 1, 'host_pattern': 'ceph-*'}
        request = NFSClusterCreateRequest.from_api('mynfs', placement=placement)
        assert request.placement == 'count:1;ceph-*'

    def test_label_placement(self):
        request = NFSClusterCreateRequest.from_api(
            'mynfs', placement={'count': 1, 'label': 'nfs'})
        assert request.placement == 'count:1;label:nfs'

    def test_string_placement_is_passed_through(self):
        request = NFSClusterCreateRequest.from_api('mynfs', placement='2 host1 host2')
        assert request.placement == '2 host1 host2'

    def test_missing_placement_is_none(self):
        request = NFSClusterCreateRequest.from_api('mynfs', placement={})
        assert request.placement is None

    @pytest.mark.parametrize('placement', [
        {'hosts': ['host1'], 'label': 'nfs'},
        {'count': 0},
        {'bogus': 1},
        ['host1'],
    ])
    def test_invalid_placement_is_rejected(self, placement):
        with pytest.raises(NFSInvalidOperation, match='placement'):
            NFSClusterCreateRequest.from_api('mynfs', placement=placement)

    def test_ingress_mode_is_converted(self):
        request = NFSClusterCreateRequest.from_api('mynfs', ingress_mode='keepalive-only')
        assert request.ingress_mode == IngressType.keepalive_only

    def test_invalid_ingress_mode_is_rejected(self):
        with pytest.raises(NFSInvalidOperation, match='ingress_mode'):
            NFSClusterCreateRequest.from_api('mynfs', ingress_mode='fast')

    def test_bind_addrs_become_a_host_to_ip_map(self):
        request = NFSClusterCreateRequest.from_api('mynfs', bind_addrs=[
            {'hostname': 'host1', 'ip': '10.0.0.5'},
            {'hostname': 'host2', 'ip': 'fe80::1'},
            {'hostname': '', 'ip': ''},
        ])
        assert request.ip_addrs == {'host1': '10.0.0.5', 'host2': 'fe80::1'}

    def test_empty_bind_addrs_are_none(self):
        assert NFSClusterCreateRequest.from_api('mynfs', bind_addrs=[]).ip_addrs is None

    @pytest.mark.parametrize('entries', [
        [{'hostname': 'host1', 'ip': ''}],
        [{'hostname': '', 'ip': '10.0.0.5'}],
        [{'hostname': 'host1', 'ip': 'not-an-ip'}],
        [{'hostname': 'host1', 'ip': '10.0.0.5'}, {'hostname': 'host1', 'ip': '10.0.0.6'}],
    ])
    def test_invalid_bind_addrs_are_rejected(self, entries):
        with pytest.raises(NFSInvalidOperation, match='bind_addrs'):
            NFSClusterCreateRequest.from_api('mynfs', bind_addrs=entries)

    def test_networks_are_cleaned(self):
        assert NFSClusterCreateRequest.from_api(
            'mynfs', networks='10.0.0.0/24').networks == ['10.0.0.0/24']
        assert NFSClusterCreateRequest.from_api(
            'mynfs', networks=[' 10.0.0.0/24 ', '']).networks == ['10.0.0.0/24']
        assert NFSClusterCreateRequest.from_api('mynfs', networks=[]).networks is None

    def test_network_with_host_bits_is_rejected(self):
        with pytest.raises(NFSInvalidOperation, match='network'):
            NFSClusterCreateRequest.from_api('mynfs', networks=['10.0.0.5/24'])

    def test_fields_are_arguments_of_create_nfs_cluster(self):
        arguments = set(inspect.signature(NFSCluster.create_nfs_cluster).parameters)
        fields = {field.name for field in dataclasses.fields(NFSClusterCreateRequest)}
        assert fields <= arguments


class TestNFSClusterCreate:
    cluster_id = 'mynfs'
    virtual_ip = '10.0.0.100/24'

    def test_existing_cluster_is_left_untouched(self):
        cluster = NFSCluster(MagicMock())
        with mock.patch('nfs.cluster.create_ganesha_pool'), \
                mock.patch('nfs.cluster.available_clusters', return_value=[self.cluster_id]), \
                mock.patch.object(cluster, 'create_empty_rados_obj') as create_obj, \
                mock.patch.object(cluster, '_call_orch_apply_nfs') as apply_nfs:
            with pytest.raises(Exception):
                cluster.create_nfs_cluster(self.cluster_id, placement=None, virtual_ip=None)
        create_obj.assert_not_called()
        apply_nfs.assert_not_called()

    def test_failed_create_removes_services_and_config(self):
        cluster = NFSCluster(MagicMock())
        with mock.patch('nfs.cluster.create_ganesha_pool'), \
                mock.patch('nfs.cluster.available_clusters', return_value=[]), \
                mock.patch('nfs.cluster.orchestrator.raise_if_exception'), \
                mock.patch.object(cluster, 'create_empty_rados_obj'), \
                mock.patch.object(cluster, 'delete_config_obj') as delete_config, \
                mock.patch.object(cluster, '_call_orch_apply_nfs',
                                  side_effect=RuntimeError('boom')):
            with pytest.raises(Exception):
                cluster.create_nfs_cluster(self.cluster_id, placement='host1', virtual_ip=None)
        removed = [call.args[0] for call in cluster.mgr.remove_service.call_args_list]
        assert removed == [f'ingress.nfs.{self.cluster_id}', f'nfs.{self.cluster_id}']
        delete_config.assert_called_once_with(self.cluster_id)

    @pytest.mark.parametrize('mode', [
        IngressType.haproxy_protocol,
        IngressType.keepalive_only,
    ])
    def test_networks_with_virtual_ip_are_rejected(self, mode):
        cluster = NFSCluster(MagicMock())
        with pytest.raises(NFSInvalidOperation, match='virtual IP'):
            cluster._call_orch_apply_nfs(
                self.cluster_id, 'host1', self.virtual_ip, mode, networks=['10.0.0.0/24'])
        cluster.mgr.apply_nfs.assert_not_called()

    def test_networks_with_haproxy_standard_are_kept(self):
        cluster = NFSCluster(MagicMock())
        with mock.patch('nfs.cluster.orchestrator.raise_if_exception'):
            cluster._call_orch_apply_nfs(
                self.cluster_id, 'host1', self.virtual_ip,
                IngressType.haproxy_standard, networks=['10.0.0.0/24'])
        spec = cluster.mgr.apply_nfs.call_args.args[0]
        assert spec.networks == ['10.0.0.0/24']
