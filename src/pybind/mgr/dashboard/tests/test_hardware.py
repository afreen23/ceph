import unittest
from unittest import mock
from urllib.parse import urlencode

from orchestrator import OrchestratorError

from ..controllers.hardware import HardwareHosts
from ..exceptions import DashboardException
from ..services.hardware import STATUS_CRITICAL, STATUS_OK, STATUS_UNKNOWN, \
    STATUS_WARNING, HardwareService
from ..tests import ControllerTestCase

# mirrors NodeProxyCache.data[host] shape.
MOCK_HOST_BLOB = {
    'host': 'host1',
    'sn': 'ABC123',
    'status': {
        'storage': {
            '1': {
                'disk-0': {'status': {'health': 'OK'}},
                'disk-1': {'status': {'health': 'Critical'}},
            }
        },
        'fans': {
            '1': {
                'fan-0': {'status': {'health': 'OK'}},
                'fan-1': {'status': {'health': 'Warning'}},
            }
        },
        'processors': {'1': {'cpu-0': {'status': {'health': 'OK'}}}},
        'memory': {'1': {'dimm-0': {'status': {'health': 'OK'}}}},
        'network': {'1': {'nic-0': {'status': {'health': 'OK'}}}},
        'power': {'1': {'psu-0': {'status': {'health': 'OK'}}}},
        'temperatures': {'1': {'temp-0': {'status': {'health': 'OK'}}}},
    },
    'firmware': {
        'id-bmc': {'name': 'BMC', 'version': '2.14'},
        'id-bios': {'name': 'BIOS', 'version': '1.8.3'},
        'id-lc': {'name': 'Lifecycle Controller', 'version': 'unknown'},
    }
}

MOCK_HARDWARE_DATA = {
    'memory': {
        'host1': {
            'SystemBoard': {
                'DIMM.Socket.A1': {
                    'description': 'DIMM DDR5',
                    'status': {'health': 'OK'}
                },
                'DIMM.Socket.A2': {
                    'description': 'DIMM DDR5',
                    'status': {'health': 'OK'}
                }
            }
        },
        'host2': {
            'SystemBoard': {
                'DIMM.Socket.A1': {
                    'description': 'DIMM DDR5',
                    'status': {'health': 'OK'}
                }
            }
        }
    },
    'storage': {
        'host1': {
            'RAID.Integrated.1': {
                'Disk.Bay.0': {
                    'description': 'SSD 960GB',
                    'status': {'health': 'OK'}
                },
                'Disk.Bay.1': {
                    'description': 'SSD 960GB',
                    'status': {'health': 'Critical'}
                }
            }
        }
    },
    'processors': {
        'host1': {
            'SystemBoard': {
                'CPU.Socket.1': {
                    'description': 'Intel Xeon',
                    'status': {'health': 'OK'}
                }
            }
        }
    },
    'network': {
        'host1': {
            'SystemBoard': {
                'NIC.Slot.1': {
                    'description': 'Ethernet 25G',
                    'status': {'health': 'OK'}
                }
            }
        }
    },
    'power': {
        'host1': {
            'SystemBoard': {
                'PSU.Slot.1': {
                    'description': 'PSU 750W',
                    'status': {'health': 'OK'}
                }
            }
        }
    },
    'fans': {
        'host1': {
            'SystemBoard': {
                'Fan.Embedded.1': {
                    'description': 'System Fan',
                    'status': {'health': 'OK'}
                }
            }
        }
    }
}

MOCK_STRING_STATUS_DATA = {
    'host1': {
        'SystemBoard': {
            'DIMM.Socket.A1': {
                'description': 'DIMM DDR5',
                'status': 'OK'
            },
            'DIMM.Socket.A2': {
                'description': 'DIMM DDR5',
                'status': 'Critical'
            }
        }
    }
}

MOCK_MISSING_STATUS_DATA = {
    'host1': {
        'SystemBoard': {
            'DIMM.Socket.A1': {
                'description': 'DIMM DDR5'
            }
        }
    }
}

MOCK_NON_DICT_COMPONENT = {
    'host1': {
        'SystemBoard': {
            'DIMM.Socket.A1': 'not-a-dict'
        }
    }
}

MOCK_WARNING_STATUS_DATA = {
    'host1': {
        'SystemBoard': {
            'DIMM.Socket.A1': {
                'description': 'DIMM DDR5',
                'status': {'health': 'OK'}
            },
            'DIMM.Socket.A2': {
                'description': 'DIMM DDR5',
                'status': {'health': 'Warning'}
            },
            'DIMM.Socket.A3': {
                'description': 'DIMM DDR5',
                'status': {'health': 'Critical'}
            }
        }
    }
}


class HardwareConstantsTest(unittest.TestCase):
    def test_status_ok_value(self):
        self.assertEqual(STATUS_OK, 'OK')

    def test_status_warning_value(self):
        self.assertEqual(STATUS_WARNING, 'Warning')

    def test_status_critical_value(self):
        self.assertEqual(STATUS_CRITICAL, 'Critical')

    def test_status_unknown_value(self):
        self.assertEqual(STATUS_UNKNOWN, 'Unknown')


class HardwareValidateCategoriesTest(unittest.TestCase):
    def test_none_returns_all(self):
        result = HardwareService.validate_categories(None)
        self.assertEqual(
            result,
            ['memory', 'storage', 'processors', 'network',
             'power', 'fans', 'temperatures']
        )

    def test_single_string_wrapped_in_list(self):
        result = HardwareService.validate_categories('memory')
        self.assertEqual(result, ['memory'])

    def test_valid_list_passes(self):
        result = HardwareService.validate_categories(['memory', 'fans'])
        self.assertEqual(result, ['memory', 'fans'])

    def test_invalid_category_raises(self):
        with self.assertRaises(DashboardException):
            HardwareService.validate_categories(['nonexistent'])

    def test_non_list_type_raises(self):
        with self.assertRaises(DashboardException):
            HardwareService.validate_categories(123)


class HardwareGetSummaryTest(unittest.TestCase):
    def _mock_common(self, data_map):
        def side_effect(category, _hostname=None):
            return data_map.get(category, {})
        return side_effect

    @mock.patch('dashboard.services.hardware.OrchClient.instance')
    def test_dict_status_health_ok(self, mock_instance):
        fake_client = mock.Mock()
        fake_client.hardware.common = self._mock_common(MOCK_HARDWARE_DATA)
        mock_instance.return_value = fake_client

        result = HardwareService.get_summary(categories=['memory'])
        cat = result['total']['category']['memory']
        self.assertEqual(cat['total'], 3)
        self.assertEqual(cat['ok'], 3)
        self.assertEqual(cat['warn'], 0)
        self.assertEqual(cat['critical'], 0)

    @mock.patch('dashboard.services.hardware.OrchClient.instance')
    def test_dict_status_health_mixed(self, mock_instance):
        fake_client = mock.Mock()
        fake_client.hardware.common = self._mock_common(MOCK_HARDWARE_DATA)
        mock_instance.return_value = fake_client

        result = HardwareService.get_summary(categories=['storage'])
        cat = result['total']['category']['storage']
        self.assertEqual(cat['total'], 2)
        self.assertEqual(cat['ok'], 1)
        self.assertEqual(cat['warn'], 0)
        self.assertEqual(cat['critical'], 1)

    @mock.patch('dashboard.services.hardware.OrchClient.instance')
    def test_string_status_format(self, mock_instance):
        fake_client = mock.Mock()
        fake_client.hardware.common = self._mock_common(
            {'memory': MOCK_STRING_STATUS_DATA}
        )
        mock_instance.return_value = fake_client

        result = HardwareService.get_summary(categories=['memory'])
        cat = result['total']['category']['memory']
        self.assertEqual(cat['ok'], 1)
        self.assertEqual(cat['warn'], 0)
        self.assertEqual(cat['critical'], 1)

    @mock.patch('dashboard.services.hardware.OrchClient.instance')
    def test_missing_status_not_counted_as_critical(self, mock_instance):
        fake_client = mock.Mock()
        fake_client.hardware.common = self._mock_common(
            {'memory': MOCK_MISSING_STATUS_DATA}
        )
        mock_instance.return_value = fake_client

        result = HardwareService.get_summary(categories=['memory'])
        cat = result['total']['category']['memory']
        self.assertEqual(cat['ok'], 0)
        self.assertEqual(cat['warn'], 0)
        self.assertEqual(cat['critical'], 0)

    @mock.patch('dashboard.services.hardware.OrchClient.instance')
    def test_non_dict_component_not_counted_as_critical(self, mock_instance):
        fake_client = mock.Mock()
        fake_client.hardware.common = self._mock_common(
            {'memory': MOCK_NON_DICT_COMPONENT}
        )
        mock_instance.return_value = fake_client

        result = HardwareService.get_summary(categories=['memory'])
        cat = result['total']['category']['memory']
        self.assertEqual(cat['ok'], 0)
        self.assertEqual(cat['warn'], 0)
        self.assertEqual(cat['critical'], 0)

    @mock.patch('dashboard.services.hardware.OrchClient.instance')
    def test_flawed_host_detected(self, mock_instance):
        fake_client = mock.Mock()
        fake_client.hardware.common = self._mock_common(MOCK_HARDWARE_DATA)
        mock_instance.return_value = fake_client

        result = HardwareService.get_summary(categories=['storage'])
        self.assertEqual(result['host']['flawed'], 1)
        self.assertTrue(result['host']['host1']['flawed'])

    @mock.patch('dashboard.services.hardware.OrchClient.instance')
    def test_healthy_host_not_flawed(self, mock_instance):
        fake_client = mock.Mock()
        fake_client.hardware.common = self._mock_common(MOCK_HARDWARE_DATA)
        mock_instance.return_value = fake_client

        result = HardwareService.get_summary(categories=['memory'])
        self.assertEqual(result['host']['flawed'], 0)
        self.assertFalse(result['host']['host1']['flawed'])
        self.assertFalse(result['host']['host2']['flawed'])

    @mock.patch('dashboard.services.hardware.OrchClient.instance')
    def test_all_categories_totals(self, mock_instance):
        fake_client = mock.Mock()
        fake_client.hardware.common = self._mock_common(MOCK_HARDWARE_DATA)
        mock_instance.return_value = fake_client

        cats = ['memory', 'storage', 'processors', 'network', 'power', 'fans']
        result = HardwareService.get_summary(categories=cats)

        totals = result['total']['total']
        self.assertEqual(totals['total'], 9)
        self.assertEqual(totals['ok'], 8)
        self.assertEqual(totals['warn'], 0)
        self.assertEqual(totals['critical'], 1)

    @mock.patch('dashboard.services.hardware.OrchClient.instance')
    def test_empty_data_returns_zeros(self, mock_instance):
        fake_client = mock.Mock()
        fake_client.hardware.common = self._mock_common({'memory': {}})
        mock_instance.return_value = fake_client

        result = HardwareService.get_summary(categories=['memory'])
        cat = result['total']['category']['memory']
        self.assertEqual(cat['total'], 0)
        self.assertEqual(cat['ok'], 0)
        self.assertEqual(cat['warn'], 0)
        self.assertEqual(cat['critical'], 0)

    @mock.patch('dashboard.services.hardware.OrchClient.instance')
    def test_warning_status_counted_separately(self, mock_instance):
        fake_client = mock.Mock()
        fake_client.hardware.common = self._mock_common(
            {'memory': MOCK_WARNING_STATUS_DATA}
        )
        mock_instance.return_value = fake_client

        result = HardwareService.get_summary(categories=['memory'])
        cat = result['total']['category']['memory']
        self.assertEqual(cat['total'], 3)
        self.assertEqual(cat['ok'], 1)
        self.assertEqual(cat['warn'], 1)
        self.assertEqual(cat['critical'], 1)


class HardwareHostsControllerTest(ControllerTestCase):
    URL = '/api/hardware/hosts'

    @classmethod
    def setup_server(cls):
        cls.setup_controllers([HardwareHosts])

    def _list(self, **params):
        self._get(f'{self.URL}?{urlencode(params)}')
        self.assertStatus(200)
        return self.json_body()

    def _make_mock_client(self, hostnames, blobs):
        """
        Build a mock OrchClient where:
          hardware.list_hosts() returns hostnames
          hardware.fullreport(hostname=h) returns { h: blobs[h] }
        """
        fake_client = mock.Mock()
        fake_client.hardware.list_hosts.return_value = hostnames
        fake_client.hardware.fullreport.side_effect = (
            lambda hostname: {hostname: blobs.get(hostname, {})}
        )
        return fake_client

    @mock.patch('dashboard.controllers.hardware.OrchClient.instance')
    def test_response_shape(self, mock_instance):
        mock_instance.return_value = self._make_mock_client(
            ['host1'], {'host1': MOCK_HOST_BLOB}
        )
        result = self._list(offset=0, limit=10)
        self.assertIsInstance(result, list)
        self.assertHeader('X-Total-Count', '1')

    @mock.patch('dashboard.controllers.hardware.OrchClient.instance')
    def test_host_summary_fields(self, mock_instance):
        mock_instance.return_value = self._make_mock_client(
            ['host1'], {'host1': MOCK_HOST_BLOB}
        )
        result = self._list(offset=0, limit=10)
        host = result[0]
        self.assertEqual(host['hostname'], 'host1')
        self.assertEqual(host['sn'], 'ABC123')
        self.assertIn('health', host)
        self.assertIn('storage', host)
        self.assertIn('fans', host)
        self.assertIn('firmware', host)

    @mock.patch('dashboard.controllers.hardware.OrchClient.instance')
    def test_storage_counts(self, mock_instance):
        # storage has 1 OK + 1 Critical -> storage.critical=1, health=Critical
        mock_instance.return_value = self._make_mock_client(
            ['host1'], {'host1': MOCK_HOST_BLOB}
        )
        result = self._list(offset=0, limit=10)
        storage = result[0]['storage']
        self.assertEqual(storage['total'], 2)
        self.assertEqual(storage['ok'], 1)
        self.assertEqual(storage['critical'], 1)
        self.assertEqual(storage['health'], STATUS_CRITICAL)

    @mock.patch('dashboard.controllers.hardware.OrchClient.instance')
    def test_fans_counts(self, mock_instance):
        # fans has 1 OK + 1 Warning -> fans.health=Warning
        mock_instance.return_value = self._make_mock_client(
            ['host1'], {'host1': MOCK_HOST_BLOB}
        )
        result = self._list(offset=0, limit=10)
        fans = result[0]['fans']
        self.assertEqual(fans['total'], 2)
        self.assertEqual(fans['ok'], 1)
        self.assertEqual(fans['warning'], 1)
        self.assertEqual(fans['health'], STATUS_WARNING)

    @mock.patch('dashboard.controllers.hardware.OrchClient.instance')
    def test_firmware_skips_unknown_version(self, mock_instance):
        # 'Lifecycle Controller' has version='unknown' -> should be excluded
        mock_instance.return_value = self._make_mock_client(
            ['host1'], {'host1': MOCK_HOST_BLOB}
        )
        result = self._list(offset=0, limit=10)
        fw = result[0]['firmware']
        self.assertIn('BMC', fw)
        self.assertIn('BIOS', fw)
        self.assertNotIn('Lifecycle Controller', fw)
        self.assertEqual(fw['BMC'], '2.14')

    @mock.patch('dashboard.controllers.hardware.OrchClient.instance')
    def test_overall_health_worst_wins(self, mock_instance):
        # storage has Critical -> overall host health must be Critical
        mock_instance.return_value = self._make_mock_client(
            ['host1'], {'host1': MOCK_HOST_BLOB}
        )
        result = self._list(offset=0, limit=10)
        self.assertEqual(result[0]['health'], STATUS_CRITICAL)

    @mock.patch('dashboard.controllers.hardware.OrchClient.instance')
    def test_pagination_total_in_header(self, mock_instance):
        # 3 hosts, limit=2 -> X-Total-Count=3, 2 hosts returned
        blobs = {f'host{i}': {**MOCK_HOST_BLOB, 'host': f'host{i}'} for i in range(3)}
        mock_instance.return_value = self._make_mock_client(
            list(blobs.keys()), blobs
        )
        result = self._list(offset=0, limit=2)
        self.assertHeader('X-Total-Count', '3')
        self.assertEqual(len(result), 2)

    @mock.patch('dashboard.controllers.hardware.OrchClient.instance')
    def test_pagination_second_page(self, mock_instance):
        # 3 hosts, offset=2 limit=2 -> 1 host on second page
        blobs = {f'host{i}': {**MOCK_HOST_BLOB, 'host': f'host{i}'} for i in range(3)}
        mock_instance.return_value = self._make_mock_client(
            list(blobs.keys()), blobs
        )
        result = self._list(offset=2, limit=2)
        self.assertEqual(len(result), 1)

    @mock.patch('dashboard.controllers.hardware.OrchClient.instance')
    def test_empty_cluster(self, mock_instance):
        mock_instance.return_value = self._make_mock_client([], {})
        result = self._list(offset=0, limit=10)
        self.assertHeader('X-Total-Count', '0')
        self.assertEqual(result, [])

    @mock.patch('dashboard.controllers.hardware.OrchClient.instance')
    def test_sort_by_hostname(self, mock_instance):
        # Hosts returned in sorted order regardless of list_hosts() order
        blobs = {f'host{i}': {**MOCK_HOST_BLOB, 'host': f'host{i}'} for i in range(3)}
        mock_instance.return_value = self._make_mock_client(
            ['host2', 'host0', 'host1'], blobs
        )
        result = self._list(offset=0, limit=10, sort='+hostname')
        hostnames = [h['hostname'] for h in result]
        self.assertEqual(hostnames, sorted(hostnames))

    @mock.patch('dashboard.controllers.hardware.OrchClient.instance')
    def test_search_by_hostname(self, mock_instance):
        # Search filters hosts
        blobs = {'web-node-01': {**MOCK_HOST_BLOB, 'host': 'web-node-01'},
                 'osd-node-01': {**MOCK_HOST_BLOB, 'host': 'osd-node-01'}}
        mock_instance.return_value = self._make_mock_client(
            list(blobs.keys()), blobs
        )
        result = self._list(offset=0, limit=10, search='osd')
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]['hostname'], 'osd-node-01')

    @mock.patch('dashboard.controllers.hardware.OrchClient.instance')
    def test_host_removed_after_listing_is_skipped(self, mock_instance):
        # host1 vanishes between list_hosts() and fullreport()
        blobs = {f'host{i}': {**MOCK_HOST_BLOB, 'host': f'host{i}'} for i in range(3)}
        fake_client = self._make_mock_client(list(blobs.keys()), blobs)

        def fullreport(hostname):
            if hostname == 'host1':
                raise OrchestratorError(f"Host '{hostname}' has no node-proxy data")
            return {hostname: blobs[hostname]}

        fake_client.hardware.fullreport.side_effect = fullreport
        mock_instance.return_value = fake_client
        result = self._list(offset=0, limit=10)
        self.assertEqual([h['hostname'] for h in result], ['host0', 'host2'])
