#!/bin/sh
# IPv4-only compose networks; managed chains only. Never flush the host ruleset.
# This service must run BEFORE Docker on boot, so restart policies cannot bypass it.
set -eu
sources='172.30.60.10 172.30.60.11 172.30.60.12 172.30.61.10 172.30.61.11 172.30.61.12'
private_ranges='0.0.0.0/8 10.0.0.0/8 100.64.0.0/10 127.0.0.0/8 169.254.0.0/16 172.16.0.0/12 192.0.0.0/24 192.0.2.0/24 192.168.0.0/16 198.18.0.0/15 198.51.100.0/24 203.0.113.0/24 224.0.0.0/4 240.0.0.0/4'

check_rules() {
    iptables -w 5 -C DOCKER-USER -j TELEIOSIS-EGRESS
    iptables -w 5 -C INPUT -j TELEIOSIS-HOST
    iptables -w 5 -C TELEIOSIS-EGRESS -m conntrack --ctstate ESTABLISHED,RELATED -j RETURN
    iptables -w 5 -C TELEIOSIS-HOST -m conntrack --ctstate ESTABLISHED,RELATED -j RETURN
    for source in $sources; do
        iptables -w 5 -C TELEIOSIS-EGRESS -s "$source" -d 172.30.61.2 -p tcp --dport 5432 -j RETURN
        iptables -w 5 -C TELEIOSIS-EGRESS -s "$source" -j TELEIOSIS-PRIVATE
        iptables -w 5 -C TELEIOSIS-HOST -s "$source" -j REJECT --reject-with icmp-admin-prohibited
    done
    for range in $private_ranges; do
        iptables -w 5 -C TELEIOSIS-PRIVATE -d "$range" -j REJECT --reject-with icmp-admin-prohibited
    done
    iptables -w 5 -C TELEIOSIS-EGRESS -m comment --comment teleiosis-egress-v1 -j RETURN
}

case "${1:-}" in
    check) check_rules; echo 'Managed egress rules are present.'; exit 0 ;;
    apply) ;;
    *) echo 'Usage: sh deploy/egress-iptables.sh apply|check' >&2; exit 2 ;;
esac
if [ "$(id -u)" -ne 0 ]; then
    echo 'Root required on the agreed Docker host.' >&2
    exit 1
fi
if iptables -w 5 -S TELEIOSIS-EGRESS >/dev/null 2>&1; then
    # Do not overwrite changed/partial rules silently.
    check_rules
    echo 'Managed egress rules already present; no changes.'
    exit 0
fi
umask 077
rules=$(mktemp)
trap 'unlink "$rules"' EXIT HUP INT TERM
{
    echo '*filter'
    echo ':DOCKER-USER - [0:0]'
    echo ':TELEIOSIS-EGRESS - [0:0]'
    echo ':TELEIOSIS-PRIVATE - [0:0]'
    echo ':TELEIOSIS-HOST - [0:0]'
    echo '-I DOCKER-USER 1 -j TELEIOSIS-EGRESS'
    echo '-I INPUT 1 -j TELEIOSIS-HOST'
    echo '-A TELEIOSIS-EGRESS -m conntrack --ctstate ESTABLISHED,RELATED -j RETURN'
    echo '-A TELEIOSIS-HOST -m conntrack --ctstate ESTABLISHED,RELATED -j RETURN'
    for source in $sources; do
        echo "-A TELEIOSIS-EGRESS -s $source -d 172.30.61.2 -p tcp --dport 5432 -j RETURN"
        echo "-A TELEIOSIS-EGRESS -s $source -j TELEIOSIS-PRIVATE"
        echo "-A TELEIOSIS-HOST -s $source -j REJECT --reject-with icmp-admin-prohibited"
    done
    for range in $private_ranges; do
        echo "-A TELEIOSIS-PRIVATE -d $range -j REJECT --reject-with icmp-admin-prohibited"
    done
    echo '-A TELEIOSIS-PRIVATE -j RETURN'
    echo '-A TELEIOSIS-HOST -j RETURN'
    echo '-A TELEIOSIS-EGRESS -m comment --comment teleiosis-egress-v1 -j RETURN'
    echo 'COMMIT'
} > "$rules"
iptables-restore --wait 5 --noflush --test < "$rules"
iptables-restore --wait 5 --noflush < "$rules"
check_rules
echo 'Applied scoped egress policy; existing host policies and SSH remain unchanged.'
