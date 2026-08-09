# Future service slots

Jellyfin is the active reference service. Nextcloud, Vaultwarden, Immich and
Pi-hole remain inactive names in `group_vars/all/service-slots.yml`.

An inactive slot reserves no RAM, IP address, disk, inventory host or LAN port.
Promoting one requires one reviewed change that supplies all of these together:

1. a unique `svc-<name>` static lease outside the dynamic DHCP range;
2. a service spec and linked permanent VM spec;
3. fixed memory and offline recovery policy;
4. an application role that installs only inside the service VM;
5. local health checks and negative tests;
6. any LAN exposure in the global allowlist plus its managed host rule;
7. backup and restore evidence through the service registry.

A new service must not reuse Jellyfin's IP, MAC, port, backup namespace or
registration receipt. DNS needs extra care: promoting Pi-hole requires reviewed
TCP/UDP 53 exposure and conflict checks against every host resolver before the
slot can become active.
