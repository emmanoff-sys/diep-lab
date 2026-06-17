#!/bin/bash
# Wrapper: fix data-dir ownership (volumes mount as root), then exec Patroni as postgres user.
set -e
mkdir -p /home/postgres/pgdata/data /wal-archive
chown -R 1000:1000 /home/postgres/pgdata /wal-archive
exec gosu postgres /usr/bin/patroni /etc/patroni/patroni-base.yml
