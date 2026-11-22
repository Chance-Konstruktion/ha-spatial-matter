"""Der Dispatch-Vertrag unter HA 2026.11: der Notify verlaesst nie den Loop.

``async_notify`` feuert ``SIGNAL_DATA_UPDATED``, und es wird aus zwei
Welten erreicht: aus dem Event-Loop (Frische-Tick, Listener) und aus
fremden Threads -- ein Dispatcher-Listener laeuft dort, wo der *Sender*
lief, und Integrationen haenden ``async_notify`` ihrer eigenen
Maschinerie aus. Seit HA 2026.11 wird der async-Versand aus jedem
anderen Thread abgebrochen, und der Hub hoert dann nichts mehr.

Gegen ein echtes Home Assistant: Der Notify wird aus einem echten
fremden Thread gerufen. HA wirft dort sonst eine Ausnahme ("calls
async_dispatcher_send from a thread other than the event loop") -- nach
der Aenderung kommt die Meldung stattdessen per ``dispatcher_send`` auf
dem Loop an, und zwar dort, wo sie hingehoert.
"""

from __future__ import annotations

import threading

from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.dispatcher import (
    async_dispatcher_connect,
    async_dispatcher_send,
)

from custom_components.spatial_matter.spatial_hub_provider import (
    SIGNAL_DATA_UPDATED,
    SpatialHubProvider,
)


async def test_notify_aus_fremdem_thread_erreicht_den_hub_auf_dem_loop(
    hass: HomeAssistant,
) -> None:
    """Ein fremder Thread darf async_notify rufen; der Versand faehrt
    ueber den Loop, nicht durch den Thread, der gerufen hat.

    Der Hub-Listener ist bewusst ein @callback: HA 2026.11 fuehrt
    plain-function-Listener ohnehin im Executor aus -- wo er laeuft,
    sagt nur der @callback zuverlaessig voraus."""
    provider = SpatialHubProvider(
        hass,
        provider_id="spatial_matter",
        name="Spatial Matter",
        data=lambda: {"nodes": [], "edges": []},
    )

    loop_thread = threading.get_ident()
    empfangen: list[str] = []
    lauforte: list[int] = []

    @callback
    def hub_listener(provider_id) -> None:
        lauforte.append(threading.get_ident())
        empfangen.append(str(provider_id))

    async_dispatcher_connect(hass, SIGNAL_DATA_UPDATED, hub_listener)

    fremde_fehler: list[Exception] = []

    def fremd() -> None:
        """Alles, was die Integration ausserhalb des Loops betreibt."""
        try:
            provider.async_notify()
        except Exception as err:  # noqa: BLE001 - die Assertion will ihn
            fremde_fehler.append(err)

    worker = threading.Thread(target=fremd, name="fremder-sender")
    worker.start()
    worker.join(timeout=5.0)
    await hass.async_block_till_done()

    assert fremde_fehler == [], (
        f"async_notify ist aus dem fremden Thread abgebrochen: "
        f"{fremde_fehler[0]}"
    )
    assert empfangen == ["spatial_matter"], (
        f"der Hub hat den Notify nicht oder falsch gehoert: {empfangen}"
    )
    assert lauforte == [loop_thread], (
        "der Hub-Listener lief nicht auf dem Event-Loop-Thread"
    )


async def test_notify_aus_dem_loop_bleibt_wie_es_war(
    hass: HomeAssistant,
) -> None:
    """Auf dem Loop aendert sich nichts: der Hub hoert sofort.

    Der Listener ist ein @callback (reihenfolgentreu auf dem Loop); ein
    plain-function-Listener liefe im Executor und die Ankunftsreihenfolge
    zweier Meldungen waere Zufall."""
    provider = SpatialHubProvider(
        hass,
        provider_id="spatial_matter",
        name="Spatial Matter",
        data=lambda: {"nodes": [], "edges": []},
    )

    empfangen: list[str] = []

    @callback
    def hub_listener(provider_id) -> None:
        empfangen.append(str(provider_id))

    async_dispatcher_connect(hass, SIGNAL_DATA_UPDATED, hub_listener)

    async_dispatcher_send(hass, SIGNAL_DATA_UPDATED, "vorher")
    provider.async_notify()
    await hass.async_block_till_done()

    # "vorher" kommt synchron, der Notify in der naechsten Loop-Runde --
    # beides ist angekommen, der Provider nur einmal gemeldet.
    assert empfangen == ["vorher", "spatial_matter"], empfangen
