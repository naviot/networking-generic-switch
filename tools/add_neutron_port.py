# Copyright 2015 Mirantis, Inc.
#
#    Licensed under the Apache License, Version 2.0 (the "License"); you may
#    not use this file except in compliance with the License. You may obtain
#    a copy of the License at
#
#         http://www.apache.org/licenses/LICENSE-2.0
#
#    Unless required by applicable law or agreed to in writing, software
#    distributed under the License is distributed on an "AS IS" BASIS, WITHOUT
#    WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See the
#    License for the specific language governing permissions and limitations
#    under the License.


import argparse
import os
import sys
import logging

from keystoneauth1 import identity
from keystoneauth1 import session
from neutronclient.v2_0 import client
from keystoneclient.v3 import client as kclient

logging.basicConfig(level=logging.INFO)
LOG = logging.getLogger('PoC')

parser = argparse.ArgumentParser(description='GenericSwitch functional test')
parser.add_argument('--switch_name',
                    type=str,
                    required=True,
                    help='Name of the switch')
parser.add_argument('--switch_id',
                    type=str,
                    required=False,
                    help='Switch id to create a local_link_information with')
parser.add_argument('--port',
                    type=str,
                    required=True,
                    help='Port to manage')
parser.add_argument('--network',
                    type=str,
                    default='private',
                    help='Neutron network name to create port in')
parser.add_argument('--auth-url',
                    type=str,
                    default='http://127.0.0.1:5000/v3',
                    help='Keystone auth URL endpoint')
parser.add_argument('--username',
                    type=str,
                    default='admin',
                    help='Keystone user name, must have admin access')
parser.add_argument('--password',
                    type=str,
                    default='admin',
                    help='Keystone user password, must have admin access')
parser.add_argument('--project-name',
                    type=str,
                    default='admin',
                    help='Keystone user project name, must have admin access')
parser.add_argument('--user-domain-id',
                    type=str,
                    help='Keystone user domain ID')
parser.add_argument('--project-domain-id',
                    type=str,
                    help='Keystone project domain ID')
parser.add_argument('--mac-address',
                    type=str,
                    help='Port mac address')
opts = parser.parse_args()


auth_params = {
    "username": os.environ.get("OS_USERNAME"),
    "password": os.environ.get("OS_PASSWORD"),
    "tenant_name": os.environ.get("OS_PROJECT_NAME"),
}


user_domain_id = os.environ.get("OS_USER_DOMAIN_ID")
if user_domain_id:
    auth_params["user_domain_id"] = user_domain_id
project_domain_id = os.environ.get("OS_PROJECT_DOMAIN_ID")
if project_domain_id:
    auth_params["project_domain_id"] = project_domain_id


auth = identity.Password(os.environ.get("OS_AUTH_URL"), **auth_params)

# auth_params = {
#     "username": os.environ.get("OS_USERNAME", opts.username),
#     "password": os.environ.get("OS_PASSWORD", opts.password),
#     "tenant_name": os.environ.get("OS_PROJECT_NAME", opts.project_name),
# }
#
# user_domain_id = os.environ.get("OS_USER_DOMAIN_ID", opts.user_domain_id)
# if user_domain_id:
#     auth_params["user_domain_id"] = user_domain_id
# project_domain_id = os.environ.get("OS_PROJECT_DOMAIN_ID",
#                                    opts.project_domain_id)
# if project_domain_id:
#     auth_params["project_domain_id"] = project_domain_id
#
#
# auth = identity.Password(os.environ.get("OS_AUTH_URL", opts.auth_url),
#                          **auth_params)


def get_network(nc, ks, name, project_name):
    networks = nc.list_networks(name=name)['networks']
    project_id = None

    for project in ks.projects.list():
        if project.name == project_name:
            project_id = project.id
            break

    for network in networks:
        if network['project_id'] == project_id and name == network['name']:
            return network


try:
    sess = session.Session(auth=auth)
    nc = client.Client(session=sess)
    ks = kclient.Client(session=sess)

    network = get_network(nc, ks, opts.network, opts.project_name)

    port_name = 'vsrx-%s' % opts.port
    create_body = {
        'port':
            {'network_id': network['id'],
             'admin_state_up': True,
             'name': port_name
             }
    }

    if opts.mac_address:
        create_body['port']['mac_address'] = opts.mac_address

    LOG.info('Create Neutron port "%s" for network "%s" vlan "%s".',
             port_name, network['name'], network['provider:segmentation_id'])
    LOG.info('Network body info: %s', create_body)

    port_id = nc.create_port(create_body)['port']['id']
    host = nc.list_agents(
        agent_type='Open vSwitch agent')['agents'][0]['host']
    update_body = {
        'port': {
            'device_owner': 'baremetal:none',
            'device_id': 'fake-instance-uuid',
            'admin_state_up': True,
            'binding:vnic_type': 'baremetal',
            'binding:host_id': host,
            'binding:profile': {
                'local_link_information': [{
                    'switch_info': opts.switch_name,
                    'switch_id': opts.switch_id or 'any_unique_value',
                    'port_id': opts.port}]
            }
        }
    }

    LOG.info('Update port "%s" with a next binding date: %s', port_name, update_body)

    nc.update_port(port_id, update_body)
except Exception as exc:
    msg = "Failed to create and update port, exception is %s" % exc
    sys.exit(msg)

