# Future service slots

M8 ships Jellyfin as the reference application brick. The remaining named
services are intentionally inactive slots in
`group_vars/all/service-slots.yml`: Nextcloud, Vaultwarden, Immich and Pi-hole.

A slot reserves no RAM, IP address, disk, inventory host or LAN port. It may not
appear in `service_dhcp_leases`, `service-specs/`, `vm-specs/`, active inventory
or the brick graph until one reviewed promotion change supplies all of the
following together:

1. a unique `svc-<name>` static lease outside the dynamic DHCP range;
2. a service spec and linked permanent standard VM spec;
3. fixed RAM and offline recovery policy;
4. an application role that installs only inside the service VM;
5. local health checks and negative tests;
6. any LAN exposure explicitly added to the global allowlist and implemented by
   the host exposure brick;
7. backup and restore evidence through the M7 registry.

Promoting one slot must not alter Jellyfin ownership or reuse its IP, MAC, port,
backup namespace or registration receipt. DNS is especially separate: Pi-hole
would require a reviewed `tcp/53` and `udp/53` exposure plus conflict checks
against every host resolver before it can become active.
