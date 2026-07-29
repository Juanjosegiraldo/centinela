# Handoff — Bloque 3: publicación de eventos (coordinación con Miguel)

> Acuerdo necesario antes de implementar la publicación al topic. La única pieza
> del pipeline que vive en los archivos de la API (`api/app/events.py`,
> `api/app/main.py`, `api/requirements.txt`). El resto (engine) ya está hecho en
> `feature-juanjo-integration`.

## 1. Contrato de transacción — no cambiar sin avisar
El engine lee estos campos tal cual están hoy en `contract.py`. Son la interfaz
compartida; renombrar o quitar alguno rompe el scoring en silencio. Congelar:

`transaction_id`, `account_id`, `amount_minor`, `currency`, `occurred_at`,
`location.lat`, `location.lon`, `merchant_id`, `merchant_category`, y el
`received_at` que agrega la API al persistir.

Si hay que cambiar alguno, se habla y se ajusta el engine en el mismo momento.

## 2. Qué publica la API y a dónde
El trigger del engine ya consume el **topic `transaction-received`** (suscripción
`scoring-engine`) y espera **el registro completo de la transacción como JSON** en
el cuerpo del mensaje (el mismo `record` que la API ya arma y persiste, incluido
`received_at`). No el id suelto — el payload completo, así el engine no depende de
leer del storage de la API.

## 3. El cambio concreto en `events.py` (identidad administrada, sin llaves)
```python
"""Event publishing for the ingestion flow."""
import json, os

try:
    from azure.identity import DefaultAzureCredential
    from azure.servicebus import ServiceBusClient, ServiceBusMessage
except ImportError:
    DefaultAzureCredential = ServiceBusClient = ServiceBusMessage = None

from . import storage

SERVICEBUS_FQDN = os.environ.get("SERVICEBUS_FQDN")
SBUS_TOPIC = os.environ.get("SBUS_TOPIC", "transaction-received")


def publish_transaction_received(record: dict) -> None:
    if ServiceBusClient is not None and SERVICEBUS_FQDN:
        client = ServiceBusClient(fully_qualified_namespace=SERVICEBUS_FQDN,
                                  credential=DefaultAzureCredential())
        with client, client.get_topic_sender(topic_name=SBUS_TOPIC) as sender:
            sender.send_messages(ServiceBusMessage(json.dumps(record)))
        return
    storage.enqueue_transaction(record["transaction_id"])  # fallback local/demo
```
Y en `main.py`, pasar el registro completo en vez del id:
```python
events.publish_transaction_received(record)   # antes: (str(tx.transaction_id))
```

## 4. Decisión pendiente: ¿mantenemos el storage queue?
Hoy `events.py` encola al **storage queue** (`q-incoming-transactions`), y el
toolkit de QA de Argenis (`consumer.py`) apunta ahí a propósito para la demo de
durabilidad. Propuesta: **publicar al topic Y mantener el enqueue al storage
queue** (el fallback de arriba lo hace solo cuando no hay Service Bus; si se
quieren ambos en la nube, se deja explícito). Así no se rompe la demo de Argenis.
¿De acuerdo, o se migra la demo al Service Bus?

## 5. Infra — ya está lista, no hay que tocarla
- Rol `Azure Service Bus Data Sender` para la identity del Web App: **ya asignado**
  en `provision-week2.sh`.
- App settings `SERVICEBUS_FQDN` y `SBUS_TOPIC`: **ya están**.
- Solo falta agregar **`azure-servicebus`** a `api/requirements.txt`.

## 6. Quién hace qué
- **Miguel:** termina semana 1-2 y hace este cambio de `events.py` + `main.py` +
  `requirements.txt` cuando su API esté estable.
- **Juanjo:** en cuanto esté, rebasa `feature-juanjo-integration` sobre develop y
  valida el end-to-end (normal → sin caso; par geo-imposible → caso; ráfaga
  velocity → regla dispara).
- Mientras tanto, el trabajo sigue en el engine, sin tocar archivos de la API,
  para avanzar sin conflictos.
