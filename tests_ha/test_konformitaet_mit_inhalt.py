"""Der volle Konformitaetssatz, gegen eine NICHT leere Nutzlast.

Die Suite nebenan prueft den Weg ohne Matter -- den Ausfallpfad. Dort ist
die Nutzlast leer, und eine leere Liste erfuellt jeden Vertrag muehelos:
keine Kennung kann wackeln, keine Kante ins Leere zeigen, keine Metadaten
sich dem Websocket verweigern. Sie beweist nichts.

Hier steht deshalb ein kleines, echtes Matter-Haus im Geraeteregister --
eine Bruecke mit zwei Lampen dahinter und ein Geraet daneben. Nichts
davon ist nachgebaut: Matter selbst braucht dieser Adapter gar nicht, er
liest ausschliesslich Config Entries, Geraeteregister und Zustaende. Das
ist der Grund, warum es hier so leicht geht -- und derselbe Grund, warum
diese Ebene auf jedem Home Assistant haelt, das Matter ueberhaupt hat.
"""

from __future__ import annotations

import pytest
from homeassistant.core import HomeAssistant
from homeassistant.helpers import (
    area_registry as ar,
    device_registry as dr,
    entity_registry as er,
)
from pytest_homeassistant_custom_component.common import MockConfigEntry
from spatial_hub_conformance import SpatialHubConformance

MATTER = "matter"
EIGENE_DOMAIN = "spatial_matter"


class TestKonformitaetMitInhalt(SpatialHubConformance):
    """Der Satz aus dem SDK an einem Haus, in dem etwas steht.

    Faellt diese Klasse, ist der Adapter vom Vertrag abgewichen -- nicht
    der Vertrag vom Adapter.
    """

    @pytest.fixture(autouse=True)
    def _haus(self, hass: HomeAssistant, enable_custom_integrations):
        bereiche = ar.async_get(hass)
        wohnzimmer = bereiche.async_create("Wohnzimmer")
        flur = bereiche.async_create("Flur")

        matter_eintrag = MockConfigEntry(domain=MATTER, title="Matter")
        matter_eintrag.add_to_hass(hass)
        geraete = dr.async_get(hass)
        entitaeten = er.async_get(hass)

        bruecke = geraete.async_get_or_create(
            config_entry_id=matter_eintrag.entry_id,
            identifiers={(MATTER, "bruecke-1")},
            name="Hue Bridge",
            manufacturer="Signify",
            model="BSB002",
        )
        geraete.async_update_device(bruecke.id, area_id=flur.id)

        # Zwei Lampen HINTER der Bruecke -- die Struktur, die diese Ebene
        # als einzige zeigt: was dunkel wird, wenn eine Kiste ausfaellt.
        for nummer in (1, 2):
            kind = geraete.async_get_or_create(
                config_entry_id=matter_eintrag.entry_id,
                identifiers={(MATTER, f"lampe-{nummer}")},
                name=f"Lampe {nummer}",
                via_device=(MATTER, "bruecke-1"),
            )
            geraete.async_update_device(kind.id, area_id=wohnzimmer.id)
            eintrag = entitaeten.async_get_or_create(
                "light", MATTER, f"lampe-{nummer}", device_id=kind.id,
                original_name=f"Lampe {nummer}",
                suggested_object_id=f"lampe_{nummer}",
            )
            hass.states.async_set(eintrag.entity_id, "on")

        # Und eines, das an nichts haengt -- sonst pruefte der Satz nur
        # den Sonderfall Bruecke.
        einzeln = geraete.async_get_or_create(
            config_entry_id=matter_eintrag.entry_id,
            identifiers={(MATTER, "steckdose-1")},
            name="Stehlampe",
        )
        geraete.async_update_device(einzeln.id, area_id=wohnzimmer.id)
        eintrag = entitaeten.async_get_or_create(
            "switch", MATTER, "steckdose-1", device_id=einzeln.id,
            original_name="Stehlampe", suggested_object_id="stehlampe",
        )
        hass.states.async_set(eintrag.entity_id, "off")

        self._hass = hass
        yield

    def build_registration(self):
        from custom_components.spatial_matter.spatial import async_setup_spatial

        eigener = MockConfigEntry(domain=EIGENE_DOMAIN, title="Spatial Matter")
        eigener.add_to_hass(self._hass)
        async_setup_spatial(self._hass, eigener)
        return self._hass.data["spatial_hub_providers"][EIGENE_DOMAIN]


def test_die_nutzlast_ist_wirklich_nicht_leer(
    hass: HomeAssistant, enable_custom_integrations
) -> None:
    """Die Gegenprobe, und der eigentliche Grund fuer diese Datei.

    Ein Konformitaetssatz ueber einer leeren Liste ist gruen und sagt
    nichts. Ohne diesen Test hier koennte die Vorrichtung oben still
    kaputtgehen -- kein Geraet mehr im Register, kein Knoten mehr in der
    Nutzlast -- und der Satz bliebe gruen, waehrend er nichts mehr prueft.

    Deshalb wird hier ausdruecklich behauptet, was drinstehen muss: drei
    Knoten und die Bruecke mit zwei Lampen dahinter.
    """
    from custom_components.spatial_matter.spatial import async_setup_spatial

    bereiche = ar.async_get(hass)
    flur = bereiche.async_create("Flur")

    matter_eintrag = MockConfigEntry(domain=MATTER, title="Matter")
    matter_eintrag.add_to_hass(hass)
    geraete = dr.async_get(hass)

    bruecke = geraete.async_get_or_create(
        config_entry_id=matter_eintrag.entry_id,
        identifiers={(MATTER, "bruecke-1")}, name="Hue Bridge",
    )
    geraete.async_update_device(bruecke.id, area_id=flur.id)
    for nummer in (1, 2):
        geraete.async_get_or_create(
            config_entry_id=matter_eintrag.entry_id,
            identifiers={(MATTER, f"lampe-{nummer}")},
            name=f"Lampe {nummer}",
            via_device=(MATTER, "bruecke-1"),
        )

    eigener = MockConfigEntry(domain=EIGENE_DOMAIN, title="Spatial Matter")
    eigener.add_to_hass(hass)
    async_setup_spatial(hass, eigener)
    nutzlast = hass.data["spatial_hub_providers"][EIGENE_DOMAIN]["data"]()

    assert len(nutzlast["nodes"]) == 3, "der Satz laeuft sonst ueber Leere"
    bruecken_knoten = f"node-{bruecke.id}"
    kinder = [
        kante for kante in nutzlast["edges"]
        if kante["source"] == bruecken_knoten
    ]
    assert len(kinder) == 2, (
        "die Bruecke muss ihre zwei Lampen tragen -- das ist die Struktur, "
        "die diese Ebene als einzige zeigt"
    )
