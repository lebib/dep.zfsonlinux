#!/usr/bin/python
# -*- coding: utf-8 -*-
#
# (c) 2013, Johan Wiren <johan.wiren.se@gmail.com>
#
# This file is part of Ansible
#
# Ansible is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# Ansible is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with Ansible.  If not, see <http://www.gnu.org/licenses/>.
#
"Ansible ZFS pool management module. See :attr:`DOCUMENTATION`."""

DOCUMENTATION = """
---
module: zpool
short_description: Manage ZFS pools
description:
  - Manages ZFS pools on Linux (other platforms untested). Can
    create/delete/manage local/foreign pools and set/get pool properties.
version_added: "2.2"
options:
  name:
    description:
      - Pool name
    required: true
  state:
    description:
      - Whether to create (C(present)), or remove (C(absent)) a file system,
        snapshot or volume.
    required: true
    choices: [present, absent]
  force_create:
    description:
      - Use `-f` when creating a new pool on devices that may contain foreign pools.
    required: false
    type: bool
    default: False
  force_destroy:
    description:
      - Use `-f` when destroying an existing pool that may be currently mounted.
    required: false
    type: bool
    default: False
  force_import:
    description:
      - Use `-f` when importing a foreign pool that may be potentially active.
    required: false
    type: bool
    default: False
  force_export:
    description:
      - Use `-f` when exporting a foreign pool that may be currently mounted.
    required: false
    type: bool
    default: False
  foreign:
    description:
      - Whether the pool is foreign (should be imported pre-configuration, and
        exported post-configuration).
    required: false
    type: bool
    default: False
  key_value:
    description:
     - Remaining options are passed as ZFS properties, converting bools to "on/off".
author: Hugo Geoffroy
"""

EXAMPLES = """
# TODO
"""

ABSENT, PRESENT = STATES = 'absent', 'present'
YES, NO, _, __ = YES_NO = 'yes', 'no', True, False

FAIL_MODES = 'wait', 'continue', 'panic'

SKIPPED_PROPS = (
    'CHECKMODE', 'name', 'state', 'foreign',
    'force_create', 'force_destroy', 'force_import', 'force_export'
)
CREATION_ONLY_OPTS = 'ashift'
IMPORT_ONLY_OPTS = 'readonly'
IMPORT_OPTS = 'readonly', 'altroot'


class Zpool(object):
    """ZFS pool management helper."""

    # Initializer
    # -------------------------------------------------------------------------

    def __init__(self, module, name, properties):
        self.module = module
        self.name = name
        self.properties = properties
        self.changes = []
        self.commands = []

    # Properties
    # -------------------------------------------------------------------------

    @property
    def zpool_path(self):
        """Path to the `zpool` binary."""
        return self.module.get_bin_path('zpool', True)

    @property
    def changed(self):
        """Whether changes were made."""
        return bool(self.changes)

    # Methods
    # -------------------------------------------------------------------------

    def exists(self):
        """Determine whether a pool exists."""
        cmd = [self.zpool_path, 'list', self.name]
        retcode, _, __ = self.run_command(' '.join(cmd), True)  # pylint: disable=invalid-name
        return not retcode

    def create(self, vdevs, force=False):
        """Create a new pool."""
        cmd = [self.zpool_path, 'create', self.name]
        if vdevs is None:
            self.fail("missing required arguments for pool creation: vdevs")
        cmd.extend(vdevs)
        if force:
            cmd.append('-f')
        for prop, value in self.properties.iteritems():
            cmd.extend(('-o', '='.join((prop, value))))
        self.run_command(' '.join(cmd))

    def destroy(self, force=False):
        """Destroy a ZFS pool."""
        cmd = [self.zpool_path, 'destroy', self.name]
        if force:
            cmd.append('-f')
        self.run_command(' '.join(cmd))

    def change(self, prop, value):
        """Changes properties on a ZFS pool."""
        cmd = [self.zpool_path, 'set', '='.join((prop, value)), self.name]
        self.run_command(' '.join(cmd))
        self.properties[prop] = value

    def attempt_import(self, force=False):
        """Attempt to import a ZFS pool."""
        cmd = [self.zpool_path, 'import', self.name, '-N']
        if force:
            cmd.append('-f')
        for prop in self.properties:
            if prop in IMPORT_OPTS:
                cmd.extend(('-o', '='.join((prop, self.properties[prop]))))
        self.run_command(' '.join(cmd))

    def export(self, force=False):
        """Export a ZFS pool."""
        cmd = [self.zpool_path, 'export', self.name]
        if force:
            cmd.append('-f')
        self.run_command(' '.join(cmd))

    def update(self, vdevs):
        """Synchronize property values."""
        current_properties, current_vdevs = self.read()
        if vdevs != current_vdevs:
            # TODO
            pass
        for prop, value in self.properties.iteritems():
            if value is None:
                self.properties[prop] = current_properties[prop]
            elif value == current_properties[prop]:
                continue
            elif prop in CREATION_ONLY_OPTS:
                self.fail(
                    "Property {} can only be set a pool creation."
                )
            elif prop in IMPORT_ONLY_OPTS:
                self.fail(
                    "Property {} can only be set at pool import."
                )
            else:
                self.change(prop, value)

    def read(self):
        """Get current pool properties."""
        cmd = [self.zpool_path, 'get', '-H', 'all', self.name]
        retcode, out, err = self.run_command(' '.join(cmd), True)
        if retcode:
            if self.module.check_mode:
                return []
            else:
                self.fail(
                    msg='Failed to get current properties ({}) : {}'
                    ''.format(' '.join(cmd), err)
                )
        else:
            return [l.split('\t')[1:3] for l in out.splitlines()]

    def run_command(self, cmd, supports_check_mode=False):
        """Run a command if module is not in check mode."""
        if supports_check_mode or not self.module.check_mode:
            retcode, err, out = self.module.run_command(cmd)
            if retcode == 127:
                self.fail(
                    "Command not found. Install ZFS or ensure you are root. ({})"
                    "".format(err or out)
                )
            if not supports_check_mode and retcode:
                self.fail(
                    "Unexpected ZFS error : {}".format(err or out),
                )
        else:
            retcode, err, out = 0, '', ''
        self.commands.append(cmd)
        if not supports_check_mode:
            self.changes.append(cmd)
        return retcode, err, out

    def fail(self, msg):
        """Fail and report in JSON."""
        self.module.fail_json(
            msg=msg,
            commands=self.commands
        )


def main():  # pylint: disable=too-many-branches
    """Module entry point."""

    module = AnsibleModule(                 # pylint: disable=undefined-variable
        argument_spec=dict(
            name=dict(type='str', required=True),
            force_create=dict(type='bool', default=False),
            force_destroy=dict(type='bool', default=False),
            force_import=dict(type='bool', default=False),
            force_export=dict(type='bool', default=False),
            foreign=dict(type='bool', default=False),
            state=dict(choices=STATES, default=PRESENT),

            # Pool creation
            ashift=dict(type='int'),

            # Pool creation & import
            altroot=dict(type='str'),

            # Pool import
            readonly=dict(choices=YES_NO),

            # Anytime
            autoexpand=dict(choices=YES_NO),
            autoreplace=dict(choices=YES_NO),
            bootfs=dict(type='str'),
            cachefile=dict(type='str'),
            comment=dict(type='str'),
            dedupditto=dict(type='int'),
            delegation=dict(choices=YES_NO),
            failmode=dict(choices=FAIL_MODES),
            listsnaps=dict(choices=YES_NO),
            version=dict(type='str'),

            # Feature flags
            enable_features=dict(type='list'),

            # Device specification
            vdevs=dict(type='list'),
        ), supports_check_mode=True
    )

    # Get module parameters
    state = module.params.get('state')
    name = module.params.get('name')
    force_create = module.params.get('force_create')
    force_destroy = module.params.get('force_destroy')
    force_import = module.params.get('force_import')
    force_export = module.params.get('force_export')
    foreign = module.params.get('foreign')
    vdevs = module.params.get('vdevs')

    # Load key-value properties
    properties = dict()
    for prop, value in module.params.iteritems():
        if prop in SKIPPED_PROPS:
            continue
        if isinstance(value, bool):
            value = 'yes' if value else 'no'
        if isinstance(value, str) and not value:
            value = None
        if value is not None:
            properties[prop] = value

    # Initialize results dictionary
    result = {}
    result['name'] = name
    result['state'] = state

    # Initialize Zpool helper
    zpool = Zpool(module, name, properties)

    if state == PRESENT:
        if foreign:
            zpool.attempt_import(force=force_import)
        if zpool.exists():
            zpool.update(vdevs)
        else:
            zpool.create(vdevs, force=force_create)
        if foreign:
            zpool.export(force=force_export)

    elif state == ABSENT:
        if foreign:
            zpool.attempt_import(force=force_import)
        if zpool.exists():
            zpool.destroy(force=force_destroy)

    result.update(zpool.properties)
    result['commands'] = zpool.commands
    result['changed'] = zpool.changed
    result['changes'] = zpool.changes
    result['check_mode'] = module.check_mode
    module.exit_json(**result)


# pylint: disable=import-error,wildcard-import,wrong-import-position
# import module snippets
from ansible.module_utils.basic import *  # NOQA
main()
