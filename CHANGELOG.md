# Changelog

## Unreleased

### Fixed
- Der Anbieter-Shim meldet Datenänderungen jetzt mit dem threadsicheren `dispatcher_send` statt `async_dispatcher_send`. HA 2026.11 verweigert den async-Versand aus jedem Thread außer dem Event-Loop, und `async_notify` wird aus beiden Welten erreicht (Loop-Tick und Dispatcher-Listener, der dort läuft, wo der Sender lief).

### Tests
- Neue Suite `test_thread_dispatch.py`: Notify aus einem echten fremden Thread muss auf dem Loop ankommen, HA-2026.11-Abbruch muss weg sein.
- Das `netz`-Fixture des SDK-Kopie-Tests stellt jetzt den Plugin-Zustand inklusive `allow_unix_socket=True` wieder her; zuvor starb jedes `hass`-Fixture alphabetisch nach `test_sdk_kopie`.

## 260808 — Erste Fassung

Erste Veröffentlichung.

Knoten aus dem Geräteregister und Bridge-Beziehungen aus `via_device`.

**Geprüft:** `data()` gegen eine Nachbildung von Geräte- und Entitätsregister
in der geforderten Form; Knoten, Kanten und Metadaten wurden gegen die
erwartete Ausgabe verglichen. Gegen eine laufende Home-Assistant-Instanz ist
diese Fassung **noch nicht** verifiziert.
