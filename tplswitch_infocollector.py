#!/usr/bin/python3
"""
Monitor TP-Link TL-SG105E with Zabbix. May cause other users to be logged out.
"""
import sys
import subprocess

REQUIRED_LIBRARIES = ["requests", "argparse", "re", "json"]

APT_PACKAGES = {
    "requests": "python3-requests",
    "argparse": "python3-argparse",
    "re": "python3-re",
    "json": "python3-json"
}

missing_libs = []

for lib in REQUIRED_LIBRARIES:
    try:
        __import__(lib)
    except ImportError:
        missing_libs.append(lib)

if missing_libs:
    print(f"Missing libraries detected: {missing_libs}. Attempting to install...")
    for lib in missing_libs:
        apt_package = APT_PACKAGES.get(lib)
        if apt_package:
            subprocess.check_call(["sudo", "apt", "install", "-y", apt_package])
        else:
            print(f"No corresponding APT package for library '{lib}'. Please install it manually.")
            sys.exit(1)


import requests
import argparse
import re
import json


class SwitchTPL:
    def __init__(self):
        self.description = None
        self.mac_address = None
        self.ip_address = None
        self.subnet_mask = None
        self.gateway = None
        self.firmware = None
        self.hardware = None
        self.port_number = 0
        self.ports = []

    def to_dict(self):
        return {
            'description': self.description,
            'mac_address': self.mac_address,
            'ip_address': self.ip_address,
            'subnet_mask': self.subnet_mask,
            'gateway': self.gateway,
            'firmware': self.firmware,
            'hardware': self.hardware,
            'ports': [port.to_dict() for port in self.ports]
        }


class SwitchPort:
    def __init__(self):
        self.port_num = 0
        self.state = 0
        self.link_status = 0
        self.txgoodpkt = 0
        self.txbadpkt = 0
        self.rxgoodpkt = 0
        self.rxbadpkt = 0

    def to_dict(self):
        return {
            'port_num': self.port_num,
            'state': self.state,
            'link_status': self.link_status,
            'txgoodpkt': self.txgoodpkt,
            'txbadpkt': self.txbadpkt,
            'rxgoodpkt': self.rxgoodpkt,
            'rxbadpkt': self.rxbadpkt
        }


class BaseSwitchParser:
    def parse_system_info(self, response_text):
        raise NotImplementedError

    def parse_ports_info(self, response_text):
        raise NotImplementedError


class SwitchTPLParser(BaseSwitchParser):

    def parse_system_info(self, response_text):
        sys_info = re.search(r'var info_ds = (\{[\s\S]*?\});$', response_text, flags=re.MULTILINE)
        json_data = re.sub(r'^(\w+):', r'"\1":', sys_info.group(1), flags=re.MULTILINE)
        return json.loads(json_data)

    def parse_ports_info(self,response_text):
        max_port_num = int(re.search(r'var max_port_num = (\d);', response_text).group(1))
        state = list(map(int, re.search(r'state:\[([\s\S]*?)\],', response_text).group(1).split(',')))
        link_status = list(map(int, re.search(r'link_status:\[([\s\S]*?)\],', response_text).group(1).split(',')))
        pkts = list(map(int, re.search(r'pkts:\[([\s\S]*?)\]', response_text).group(1).split(',')))

        state_info = ["Disabled", "Enabled"]
        link_info = ["Link Down", "Auto", "10Half", "10Full", "100Half", "100Full", "1000Full", ""]

        ports_info = {}

        for index in range(max_port_num):
            port_id = index + 1
            ports_info[port_id] = {
                'status': state_info[state[index]],
                'link-status': link_info[link_status[index]],
                'txgoodpkt': pkts[4 * index],
                'txbadpkt': pkts[4 * index + 1],
                'rxgoodpkt': pkts[4 * index + 2],
                'rxbadpkt': pkts[4 * index + 3]
            }

        return ports_info


class SwitchTPLDAO:
    def __init__(self, switch_parser: BaseSwitchParser):
        self.switch = SwitchTPL()
        self.parser = switch_parser
        self.url = None
        self.username = None
        self.password = None

    def get_switch(self):
        return self.switch

    def logon(self):
        data = {
            'username': self.username,
            'password': self.password,
            'logon': 'Login',
        }

        session = requests.Session()
        response = session.post(self.url + 'logon.cgi', data=data)

        if response.status_code == 200:
            return session
        else:
            raise Exception(f'Login failed. HTTP Status Code: {response.status_code}')

    def sys_info_loader(self, session):
        response = session.get(self.url + 'SystemInfoRpm.htm')
        sys_info = self.parser.parse_system_info(response.text)

        self.switch.description = sys_info['descriStr']
        self.switch.mac_address = sys_info['macStr']
        self.switch.ip_address = sys_info['ipStr']
        self.switch.subnet_mask = sys_info['netmaskStr']
        self.switch.gateway = sys_info['gatewayStr']
        self.switch.firmware = sys_info['firmwareStr']
        self.switch.hardware = sys_info['hardwareStr']

    def ports_info_loader(self, session):
        response = session.get(self.url + 'PortStatisticsRpm.htm')
        ports_info = self.parser.parse_ports_info(response.text)

        self.switch.ports = []

        for port_id, port_data in ports_info.items():
            port = SwitchPort()
            port.port_num = port_id
            port.state = port_data['status']
            port.link_status = port_data['link-status']
            port.txgoodpkt = port_data['txgoodpkt']
            port.txbadpkt = port_data['txbadpkt']
            port.rxgoodpkt = port_data['rxgoodpkt']
            port.rxbadpkt = port_data['rxbadpkt']

            self.switch.ports.append(port)


def argparse_baseconfig ():
    cli_parser = argparse.ArgumentParser(
        prog='TP-Link TL-SG105E Data-Collector',
        description="Collect System and Ports Information from a TP-Link TL-SG105E Switch")

    cli_parser.add_argument('-url', '--url', type=str, help='Switch url: http://[IP_or_domain]:[port_if_needed]/')
    cli_parser.add_argument('-usr', '--user', type=str, help='Switch user to logon')
    cli_parser.add_argument('-passwrd', '--password',type=str, help='Switch user password to logon')

    args = cli_parser.parse_args()

    return args


if __name__ == '__main__':

    def_cli_parser = argparse_baseconfig()

    def_switch_parser = SwitchTPLParser()
    stpl = SwitchTPLDAO(def_switch_parser)

    stpl.url = def_cli_parser.url
    stpl.username = def_cli_parser.user
    stpl.password = def_cli_parser.password

    s = stpl.logon()

    stpl.sys_info_loader(s)
    stpl.ports_info_loader(s)

    switch = stpl.get_switch()

    switch_info_json = json.dumps(switch.to_dict(), indent=4)
    print(switch_info_json)

    with open('switch_info.json', 'w') as f:
        f.write(switch_info_json)