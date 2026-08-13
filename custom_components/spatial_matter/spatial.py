"""Matter on the floor plan: nodes, and the bridges they hang behind.

Matter is the odd one out here, and it is worth saying why rather than
inventing something to draw.

Z-Wave and Zigbee are meshes that keep routing tables, so a mesh map is
the natural picture. Matter is not a radio -- it is an application layer
that rides on Wi-Fi or on Thread. A Matter node on Wi-Fi has no topology
at all beyond "it is on the network", and a Matter node on Thread routes
through a border router that **the Thread layer already draws**. Inventing
a star here, with every node on a line to a controller that is not a radio
and does not route anything, would be a picture of nothing.

What Matter really does have, and what nothing in Home Assistant shows, is
**bridges**. A Hue bridge or an Aqara hub exposes a dozen devices over
Matter, and Home Assistant records that relationship as ``via_device`` when
it creates them. That is genuine structure -- it says which twelve lamps go
dark when one box is unplugged -- and it is the whole content of this
layer. Everything else is each node sitting in the room the user put it in.

So this file reads the config entries and the device registry, and stops
there. No integration internals, no fallback, nothing to fall back *from*:
what it draws is public, stable, and true on every Home Assistant that has
Matter at all. Availability comes from whether a node's entities are
answering, which is the same thing an unreachable node's entities say
anyway.

Which devices are Matter is asked via the **config entries**, never via
``identifiers`` -- an integration is free to identify its devices however
it likes, and the entry a device was created under is always true.
"""

from __future__ import annotations

from datetime import timedelta
from typing import Any

from homeassistant.core import HomeAssistant
from homeassistant.helpers import (
    device_registry as dr,
    entity_registry as er,
)
from homeassistant.helpers.event import async_track_time_interval

from .spatial_hub_provider import edge, node, spatial_provider

MATTER_DOMAIN = "matter"

# Availability is what changes here, and it changes through entity states
# rather than any signal this integration could subscribe to.
REFRESH = timedelta(seconds=30)

_UNREACHABLE = {"unavailable", "unknown", ""}


def _devices(hass: HomeAssistant) -> dict[str, Any]:
    """Every device Home Assistant created under a Matter config entry."""
    try:
        registry = dr.async_get(hass)
    except (AttributeError, KeyError):  # pragma: no cover - registry absent
        return {}
    devices: dict[str, Any] = {}
    for entry in hass.config_entries.async_entries(MATTER_DOMAIN):
        for device in dr.async_entries_for_config_entry(registry, entry.entry_id):
            devices[device.id] = device
    return devices


def _entities_of(hass: HomeAssistant, device_id: str) -> list[Any]:
    """The node's own entities -- the ones Matter itself reports.

    A device is not one integration's property. A lamp reached over Matter
    *and* over its vendor's own cloud integration carries entities from
    both, and the cloud one keeps answering long after the local node has
    dropped off the network. Counting it would paint a dead node green.
    """
    try:
        registry = er.async_get(hass)
    except (AttributeError, KeyError):  # pragma: no cover
        return []
    return [
        entry
        for entry in getattr(registry, "entities", {}).values()
        if getattr(entry, "device_id", None) == device_id
        and getattr(entry, "platform", MATTER_DOMAIN) == MATTER_DOMAIN
        and not getattr(entry, "disabled_by", None)
    ]


def _representative(entries: list[Any]) -> str | None:
    """One entity to stand for the node, so its popup has a door.

    Without one the popup is a card with a name on it and nothing to open.
    Diagnostics sort last: "Firmware" is a poor answer to "show me this".
    """
    if not entries:
        return None
    return sorted(
        entries,
        key=lambda entry: (
            getattr(entry, "entity_category", None) is not None,
            entry.entity_id,
        ),
    )[0].entity_id


def _reachable(hass: HomeAssistant, entries: list[Any]) -> str:
    """A node is up if any of its entities is answering.

    "Any" rather than "all" on purpose: a node can have one attribute that
    has never reported while the node itself is perfectly reachable, and
    requiring all of them would paint working devices red.
    """
    if not entries:
        return "unknown"
    for entry in entries:
        state = hass.states.get(entry.entity_id)
        if state and str(state.state).lower() not in _UNREACHABLE:
            return "online"
    return "offline"


def _label(device: Any) -> str:
    return (
        getattr(device, "name_by_user", None)
        or getattr(device, "name", "")
        or "Matter Gerät"
    )


def async_setup_spatial(hass: HomeAssistant, entry: Any) -> None:
    def data() -> dict[str, list]:
        devices = _devices(hass)
        if not devices:
            return {"nodes": [], "edges": []}

        # Who hangs behind whom. Only counted within Matter: a Matter device
        # can sit behind something this layer does not draw, and an edge to
        # a node that is not there is a line to nowhere.
        children: dict[str, list[str]] = {}
        for device in devices.values():
            parent = getattr(device, "via_device_id", None)
            if parent in devices:
                children.setdefault(parent, []).append(device.id)

        nodes = []
        edges = []
        for device in sorted(devices.values(), key=lambda device: device.id):
            entries = _entities_of(hass, device.id)
            state = _reachable(hass, entries)
            bridged = children.get(device.id, [])
            is_bridge = bool(bridged)
            nodes.append(
                node(
                    f"node-{device.id}",
                    label=_label(device),
                    area_id=getattr(device, "area_id", None),
                    # The door into Home Assistant itself. The hub fills in
                    # the device behind the entity on its own.
                    entity_id=_representative(entries),
                    state=state,
                    icon=(
                        "mdi:bridge" if is_bridge
                        else "mdi:lan-connect" if state == "online"
                        else "mdi:lan-disconnect"
                    ),
                    rolle="Bridge" if is_bridge else "Gerät",
                    hersteller=getattr(device, "manufacturer", "") or "",
                    modell=getattr(device, "model", "") or "",
                    firmware=getattr(device, "sw_version", "") or "",
                    hardware=getattr(device, "hw_version", "") or "",
                    entitaeten=len(entries),
                    # The number that makes a bridge worth finding on a
                    # plan: how much goes dark with it.
                    **({"dahinter": len(bridged)} if is_bridge else {}),
                )
            )
            for child in bridged:
                edges.append(
                    edge(
                        f"node-{device.id}",
                        f"node-{child}",
                        quality="unknown",
                        # Directed, because this really is one way round:
                        # the bridge carries the device, not the reverse.
                        directed=True,
                    )
                )

        return {"nodes": nodes, "edges": edges}

    provider = spatial_provider(
        hass,
        entry,
        name="Matter",
        icon="mdi:lan-connect",
        data=data,
        version="260808",
    )

    entry.async_on_unload(
        async_track_time_interval(
            hass, lambda _now: provider.async_notify(), REFRESH
        )
    )
