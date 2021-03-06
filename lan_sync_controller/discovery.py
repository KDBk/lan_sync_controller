from __future__ import absolute_import, division, print_function
import errno
import logging
import math
import socket

import scapy.config
import scapy.layers.l2
import scapy.route
from scapy.all import *

from lan_sync_controller.config_loader import SETTINGS

LOG = logging.getLogger(__name__)


def long2net(arg):
    """Convert long to netmask"""
    if (arg <= 0 or arg >= 0xFFFFFFFF):
        raise ValueError("illegal netmask value", hex(arg))
    return 32 - int(round(math.log(0xFFFFFFFF - arg, 2)))


def to_CIDR_notation(bytes_network, bytes_netmask):
    network = scapy.utils.ltoa(bytes_network)
    netmask = long2net(bytes_netmask)
    net = "%s/%s" % (network, netmask)
    if netmask < 16:
        LOG.warning("%s is too big. skipping" % net)
        return None

    return net


def scan_and_get_neighbors(net, interface, timeout=1):
    """Get list interfaces, then scan in each network
    and get available neighbors. Actually, it will  ping`
    to each ip in network, then wait for reply (received packet)
    :param net: (string)
    :param interface: (string)
    :param timeout(integer)
    """
    LOG.info('arping %s on %s' % (net, interface))

    try:
        ans, unans = scapy.layers.l2.arping(net, iface=interface,
                                            timeout=timeout,
                                            verbose=True)
        neighbors = []
        for s, r in ans.res:
            neighbors.append(r.sprintf('%ARP.psrc%'))
        return neighbors
    except socket.error as e:
        if e.errno == errno.EPERM:
            LOG.error('%s. Did you run as root?' % (e.strerror))
        else:
            raise


def scan_udp_port(dst_ip, dst_port, dst_timeout=1):
    """Scan UDP port with specific ip address and port
    This host run code will be source host, define destination
    host and port that you want to scan.
    :param dst_ip: (string) destination ip address
    :param dst_port: (integer) specific port
    :param dst_timeout: (integer)
    """
    udp_scan_resp = sr1(IP(dst=dst_ip) / UDP(dport=dst_port),
                        timeout=dst_timeout)
    if str(type(udp_scan_resp)) == "<type 'NoneType'>":
        retrans = []
        for count in range(0, 3):
            retrans.append(sr1(IP(dst=dst_ip) / UDP(dport=dst_port),
                               timeout=dst_timeout))
            for item in retrans:
                if str(type(item)) != "<type 'NoneType'>":
                    scan_udp_port(dst_ip, dst_port, dst_timeout)
            return 'Open|Filtered'
    elif udp_scan_resp.haslayer(UDP):
        return 'Open'
    elif udp_scan_resp.haslayer(ICMP):
        if int(udp_scan_resp.getlayer(ICMP).type) == 3 and \
                int(udp_scan_resp.getlayer(ICMP).code) == 3:
            return 'Closed'
        elif int(udp_scan_resp.getlayer(ICMP).type) == 3 and \
                int(udp_scan_resp.getlayer(ICMP).code) in [1, 2, 9, 10, 13]:
            return 'Filtered'
        else:
            return 'CHECK'


class NeighborsDetector(object):

    def __init__(self):
        self.port = SETTINGS['default-port']

    def get_all_neighbors(self):
        """Get All Available Neighbors in LAN"""
        result = {}
        for network, netmask, _, interface, address in \
                scapy.config.conf.route.routes:
            # skip loopback network and default gw
            if network == 0 or interface == 'lo' or \
                    address == '127.0.0.1' or address == '0.0.0.0':
                continue

            if netmask <= 0 or netmask == 0xFFFFFFFF:
                continue

            net = to_CIDR_notation(network, netmask)

            if interface != scapy.config.conf.iface:
                msg = ('Skipping %s because scapy currently doesn\'t\
                       support arping on non-primary network \
                       interfaces' % net)
                LOG.warning(msg)
                continue

            if net:
                result[interface] = scan_and_get_neighbors(net, interface)
        return result

    def detect_valid_hosts(self):
        """Detect valid host, which open a given port"""
        neighbors = self.get_all_neighbors()
        valid_host = []
        for neighbor in neighbors.values():
            for _n_ip in neighbor:
                # If the given host opens port, get it.
                if 'Open' in scan_udp_port(_n_ip, self.port):
                    LOG.info('Valid Host was founded: %s' % _n_ip)
                    valid_host.append(_n_ip)
        return valid_host
