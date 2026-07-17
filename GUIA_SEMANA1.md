# Centinela — Guía paso a paso Semana 1 (costo mínimo)

Esta guía cubre los 4 temas de la semana (Nube/Azure, Identidad, Redes+VM, App Service — más Storage del día 5) y mapea cada paso a los 26 entregables del documento `Azure-Semana1.md`. Todo se hace con la **suscripción gratuita** y el gasto total proyectado de la semana es **≈ 3–9 USD**, muy por debajo del límite de 20 USD.

---

## Paso 0 — Activar la suscripción HOY (Entregable 1)

Estás dentro del tenant de la Universidad de Medellín pero **sin suscripción**. El documento exige que la suscripción se cree el primer día del proyecto. Tienes dos opciones desde la pantalla de bienvenida que ya ves:

**Opción A — Azure for Students (recomendada si tu correo institucional verifica):**
1. Clic en **"Microsoft Azure for Students" → Inicio**.
2. Verifica tu estado académico con el correo de la universidad.
3. Obtienes **100 USD por 12 meses, sin tarjeta de crédito** y con límite de gasto que no se puede desactivar. Es la opción más segura contra cobros.

**Opción B — Prueba gratuita (la que describe literalmente el documento):**
1. Clic en **"Empiece con una prueba gratuita de Azure" → Inicio**.
2. Requiere tarjeta (solo verificación, no cobra). Da **200 USD por 30 días** con límite de gasto activado.
3. Si eliges esta, anota la fecha: el proyecto dura 21 días y la vigencia es 30 — hay margen, pero justo.

**Evidencia a capturar:** pantallazo de la suscripción activa en *Suscripciones*, y del **límite de gasto** (Suscripción → Información general: "Límite de gasto: Activado"). Documenta su comportamiento: al agotarse el crédito, Azure **deshabilita la suscripción y detiene los servicios** en lugar de cobrar — no hay sorpresa en la factura, pero el sistema queda caído hasta el siguiente ciclo o hasta quitar el límite.

## Paso 1 — Presupuesto y alertas (Entregable 1)

Portal → **Cost Management + Billing → Presupuestos → Agregar**:
1. Ámbito: tu suscripción. Nombre: `budget-centinela`. Monto: **20 USD** mensuales (es el techo que el criterio de aceptación impone para la semana).
2. Alertas: **50 % (10 USD)** — aviso temprano a mitad de camino; **80 % (16 USD)** — frenar y revisar qué quedó encendido; **100 % (20 USD)** — violación del criterio de aceptación, ejecutar `shutdown.sh --full` de inmediato.
3. Correo de alerta: el tuyo.

**Evidencia:** pantallazo del presupuesto con los tres umbrales y su justificación escrita (la de arriba te sirve).

## Paso 2 — Región e informe de cuotas (Entregables 2 y 3)

**Región recomendada: `eastus`** (East US). Justificación para tu documento:
- **Latencia:** ~60–80 ms desde Colombia, la mejor de las regiones con catálogo completo (Brazil South es más cercana pero 20–40 % más cara y con frecuencia sin cuota en suscripciones gratuitas).
- **Disponibilidad verificada:** East US tiene App Service Linux, Storage, Azure SQL, Cosmos DB, Service Bus y **Azure AI Document Intelligence** (el "servicio de reconocimiento documental" que exige Centinela para la verificación de identidad, con nivel gratuito F0: 500 páginas/mes). Verifícalo tú mismo, no lo asumas: Portal → buscar **"Document Intelligence" → Crear** → confirma que East US aparece en la lista de regiones y que el SKU **F0 (Free)** está seleccionable. Pantallazo = evidencia. No hace falta crearlo esta semana.
- **Costo:** East US es de las regiones más baratas del catálogo de Azure.

**Informe de cuotas** (el crédito y la cuota son controles independientes — puede haber saldo y cuota cero). En **Cloud Shell** (icono `>_` en la barra superior del portal; elige Bash y storage efímero para no crear una cuenta de almacenamiento extra):

```bash
# Capacidad de cómputo disponible (vCPUs por familia)
az vm list-usage --location eastus -o table | head -30

# ¿Qué familias tienen cuota CERO? (típico en free/students: muchas)
az vm list-usage --location eastus --query "[?limit=='0'].{Familia:name.localizedValue}" -o table

# Disponibilidad y SKUs de Document Intelligence en la región
az cognitiveservices account list-skus --kind FormRecognizer --location eastus -o table
```

**Evidencia:** documento con las tres secciones que pide 2.1 (cómputo disponible, Document Intelligence en la región, servicios con cuota cero). Este informe condiciona las semanas 2 y 3 — hazlo antes de decidir nada más.

## Paso 3 — Convención de nombres (Entregable 6)

Documenta esta convención (ya está aplicada en los scripts):

Patrón general: `<tipo>-<proyecto>-<carga>-<ambiente>`, con `proyecto = ctn` y `ambiente = dev`. Ejemplos: `rg-ctn-dev`, `vnet-ctn-dev`, `snet-app`, `nsg-ctn-data-dev`, `plan-ctn-dev`, `app-ctn-ingesta-dev-jj15`, `stctndevjj15`.

**Caso de unicidad global:** las cuentas de almacenamiento (`*.blob.core.windows.net`) y las webapps (`*.azurewebsites.net`) comparten espacio de nombres con todo Azure. Se resuelve añadiendo un **sufijo único** (`jj15`, tus iniciales+número) declarado como parámetro `SUFIJO_UNICO` en el script. Storage además prohíbe guiones: por eso `stctndevjj15` va sin separadores.

## Paso 4 — Clasificación de componentes (Entregable 7)

A partir del recorrido de la transacción del documento Centinela:

| Componente | Servicio Azure | Modelo | Responsabilidad de la célula | Responsabilidad de Azure |
|---|---|---|---|---|
| API de ingesta | App Service | PaaS | Código, contrato, configuración | SO, parches, runtime, HTTPS |
| Transacciones crudas / evidencia | Blob Storage | PaaS | Datos, ciclo de vida, permisos | Durabilidad, replicación LRS |
| Cola de ingesta | Storage Queue | PaaS | Formato de mensaje, política de fallos | Disponibilidad de la cola |
| Red privada | VNet/Subnets/NSG | IaaS | Topología, rangos, reglas | Fabric de red físico |
| Identidades y roles | Microsoft Entra ID | SaaS | Asignación de roles, menor privilegio | Autenticación, tokens |
| Almacén relacional (S2) | Azure SQL | PaaS | Esquema, consultas | Motor, backups |
| Almacén de casos (S2) | Cosmos DB | PaaS | Modelo de partición | Distribución, SLA |
| Mensajería de eventos (S2) | Service Bus / Queue | PaaS | Tópicos, consumidores | Broker |
| Reconocimiento documental (S3) | Document Intelligence | SaaS | Envío del doc, uso del resultado | Modelo de IA completo |

## Paso 5 — Ejecutar el aprovisionamiento (Entregables 4, 9, 12, 13, 19, 21)

1. Sube la carpeta del repo a Cloud Shell (o clónala de tu GitHub — el documento exige que el script esté **versionado**; haz el commit primero).
2. Edita las variables del inicio de `infra/provision.sh` (`SUFIJO_UNICO` sobre todo).
3. Ejecuta:

```bash
cd centinela/infra
bash provision.sh
```

Crea, en orden: grupo de recursos → VNet `10.10.0.0/16` con `snet-app /26` (delegada a App Service, con service endpoint de Storage), `snet-data /27` y `snet-ops /27` → NSGs con **denegar por defecto** y reglas justificadas → cuenta de almacenamiento **LRS** con contenedores `transacciones-crudas` y `docs-verificacion`, cola `q-transacciones-entrantes` y política de ciclo de vida → plan **B1 Linux** + Web App Python con **identidad gestionada** e integración de VNet → asignaciones de rol → y al final **cierra el firewall del storage** (`default-action Deny`, solo `snet-app`).

Decisiones ya justificadas dentro del script (cópialas a tu doc de arquitectura):
- **B1** es el nivel más bajo con integración de VNet (F1 y D1 no la soportan) → requisito 2.9. Costo: ~0.018 USD/h ≈ **13 USD/mes si corre 24/7**; con el script de apagado cada noche, la semana cuesta **3–5 USD**.
- **LRS** es la redundancia más económica; 3 copias en un datacenter bastan para preservar evidencia en un proyecto de 21 días (documenta que producción real usaría ZRS/GRS).
- **Subred de app /26**: el mínimo para VNet integration es /28 (16 IPs), pero el escalado de la semana 3 consume una IP por instancia; /26 (64 IPs) da margen. Esa es la "verificación del tamaño mínimo" que pide 2.7.
- **Service endpoints** (gratis) vs **Private Endpoint** (~7 USD/mes + tráfico): el endpoint de servicio enruta el tráfico de la subred por la red troncal de Azure y el firewall del storage solo acepta esa subred; el private endpoint además le da al storage una IP privada dentro de tu VNet y elimina por completo su IP pública. Para el presupuesto de Centinela, service endpoints — y esa comparación es exactamente lo que pide el documento.

**Idempotencia:** vuelve a ejecutar `bash provision.sh` — debe terminar sin errores ni efectos adversos (criterio de aceptación). Caso documentado: `az role assignment create` no es idempotente y se tolera con `|| true`.

## Paso 6 — Desplegar la API (Entregables 15, 16, 17, 18)

```bash
cd ../api
zip -r ../api.zip .
az webapp deploy -g rg-ctn-dev -n app-ctn-ingesta-dev-jj15 --src-path ../api.zip --type zip
```

Espera 2–3 minutos (Oryx instala dependencias). Luego prueba (esto es tu **evidencia** de los criterios de ingesta):

```bash
APP="https://app-ctn-ingesta-dev-jj15.azurewebsites.net"

# Transacción VÁLIDA -> 202
curl -s -o /dev/null -w "%{http_code}\n" -X POST $APP/transactions \
 -H "Content-Type: application/json" -d '{
  "transaction_id":"11111111-1111-4111-8111-111111111111",
  "account_id":"acct-001","amount_minor":1250000,"currency":"COP",
  "occurred_at":"2026-07-17T14:00:00Z",
  "location":{"lat":6.2442,"lon":-75.5812},
  "merchant_id":"m-77","merchant_category":"grocery"}'

# Inválidas -> 400 en todos los casos (cambia un campo por prueba):
#  monto negativo: "amount_minor":-5
#  marca futura:   "occurred_at":"2030-01-01T00:00:00Z"
#  coordenadas:    "location":{"lat":99,"lon":0}
#  campo extra:    añade "hack":"x"
#  campo ausente:  borra "account_id"

# Carga de documento (validación por magic bytes, nombre generado por el sistema):
printf '%%PDF-1.4 contenido de prueba' > prueba.pdf
curl -s -X POST $APP/cases/CASE-001/documents -F "file=@prueba.pdf"      # -> 201
printf 'MZ ejecutable' > malicioso.pdf
curl -s -o /dev/null -w "%{http_code}\n" -X POST $APP/cases/CASE-001/documents -F "file=@malicioso.pdf"  # -> 415

# Recuperar la transacción persistida por su identificador (criterio de aceptación).
# Ojo: desde Cloud Shell el storage está bloqueado (¡esa es la prueba de aislamiento!).
# Para verificar la persistencia, agrega temporalmente TU IP al firewall:
az storage account network-rule add -g rg-ctn-dev --account-name stctndevjj15 --ip-address $(curl -s ifconfig.me)
az storage blob list --account-name stctndevjj15 -c transacciones-crudas --auth-mode login -o table
az storage account network-rule remove -g rg-ctn-dev --account-name stctndevjj15 --ip-address $(curl -s ifconfig.me)
```

La tabla de códigos de estado (entregable 18) está en el docstring de `api/app/main.py`; el contrato con las 4 decisiones justificadas (entregable 15), en `api/app/contract.py`. Justificación del nivel de servicio (entregable 17): B1 = mínimo con VNet integration; 21 días × apagado nocturno (~10 h/día encendido) ≈ **3.8 USD**; 24/7 sería ≈ 9 USD — ambos bajo presupuesto.

## Paso 7 — Prueba de aislamiento de la capa de datos (Entregable 14)

Desde tu navegador (fuera de la VNet) intenta abrir:
`https://stctndevjj15.blob.core.windows.net/transacciones-crudas/11111111-1111-4111-8111-111111111111.json`

Resultado esperado: **403 AuthorizationFailure** — y desde el portal, la lista de blobs también fallará ("no tienes acceso desde esta red"). Pantallazo de ambos = evidencia. La API, en cambio, sí escribe: está dentro de `snet-app`, la única subred admitida por el firewall del storage.

## Paso 8 — Identidad: matriz, pruebas negativas y nota conceptual (Entregables 8, 10, 11)

**Matriz de roles** (cada permiso con la operación que lo justifica):

| Rol | Rol de Azure asignado | Plano | Operación del sistema que lo justifica |
|---|---|---|---|
| Servicio (MI de la webapp) | Storage Blob Data Contributor (scope: storage) | Datos | Persistir transacción cruda; guardar documento de verificación |
| Servicio | Storage Queue Data Contributor (scope: storage) | Datos | Encolar transacción para el motor (Semana 2) |
| Analista | Reader (scope: RG) | Control | Ver el estado de los recursos sin modificarlos |
| Analista | Storage Blob Data Reader (scope: storage) | Datos | Leer la evidencia de un caso |
| Administrador | Contributor (scope: RG) | Control | Aprovisionar y configurar la infraestructura |
| Auditor | Reader (scope: RG) | Control | Ver todo, modificar nada |

Nota: el rol Servicio **no** tiene Contributor ni ningún permiso de plano de control — por eso la prueba "Servicio intenta crear un recurso → Denegado" pasa sin configurar nada extra.

**Usuarios de prueba.** Estás en el tenant de la universidad y probablemente **no puedes crear usuarios** en él (necesitas rol de administrador del tenant). Alternativas, de mejor a peor: (a) si al activar la suscripción Azure te creó un **directorio propio** (revisa Configuración → Directorios), crea ahí `analista@…onmicrosoft.com` y `auditor@…`; (b) invita como **invitados (B2B)** dos correos personales tuyos (Entra ID → Usuarios → Invitar); (c) si nada de eso es posible, documenta la limitación del tenant y ejecuta la prueba del rol Servicio (que no requiere usuarios) más las dos humanas con un compañero de la célula como invitado. Pasa los Object IDs al script vía `OID_ANALISTA=... OID_AUDITOR=... bash provision.sh` para que las asignaciones queden **creadas desde el script**, como exige 2.6.

**Bitácora de pruebas negativas (3 mínimo):**
1. Sesión como *Analista* → Portal → la webapp → Configuración → intentar cambiar un app setting → **Denegado** (Reader no tiene `Microsoft.Web/sites/config/write`). Pantallazo.
2. Sesión como *Auditor* → intentar detener la webapp o borrar un recurso → **Denegado**. Pantallazo.
3. *Servicio*: desde la consola SSH de la webapp (Portal → webapp → SSH), obtener token de la identidad gestionada e intentar crear un recurso vía ARM → **403 AuthorizationFailed** (la MI no tiene roles de plano de control):
```bash
TOKEN=$(curl -s -H "X-IDENTITY-HEADER: $IDENTITY_HEADER" "$IDENTITY_ENDPOINT?resource=https://management.azure.com/&api-version=2019-08-01" | python3 -c "import sys,json;print(json.load(sys.stdin)['access_token'])")
curl -s -X PUT "https://management.azure.com/subscriptions/<SUB_ID>/resourceGroups/rg-hackeo?api-version=2021-04-01" -H "Authorization: Bearer $TOKEN" -H "Content-Type: application/json" -d '{"location":"eastus"}'
```

**Nota autenticación vs autorización (aplícala tal cual):** la **autenticación** ocurre en Microsoft Entra ID — ejemplo: la webapp presenta su identidad gestionada al endpoint de identidad y Entra emite un token que prueba *quién es*; no hay contraseña que la célula administre. La **autorización** ocurre en el recurso al evaluar RBAC — ejemplo: el storage recibe el token y verifica si ese principal tiene `Storage Blob Data Contributor` sobre esa cuenta antes de aceptar el `PUT` del blob; el Auditor se autentica perfectamente (Entra lo reconoce) pero al intentar borrar un recurso la autorización falla porque Reader no incluye la acción `*/delete`.

## Paso 9 — Cola, garantías de entrega e idempotencia (Entregables 21, 22, 23)

Validar escritura/lectura (con tu IP temporalmente en el firewall, como en el paso 6):

```bash
az storage message put  --account-name stctndevjj15 -q q-transacciones-entrantes --content "hola-centinela" --auth-mode login
az storage message get  --account-name stctndevjj15 -q q-transacciones-entrantes --auth-mode login
```

**Documento de garantías (los tres escenarios de 2.11):**
- *Consumidor lee y falla antes de confirmar:* el mensaje queda invisible durante el `visibility timeout` (30 s por defecto); al vencer, **reaparece** en la cola y otro consumidor lo procesa. Nada se pierde; puede procesarse dos veces → por eso el consumidor debe ser idempotente.
- *Mensaje falla reiteradamente:* Storage Queue expone `DequeueCount`. Política definida: al superar **5 intentos**, el consumidor lo mueve a una cola `q-transacciones-veneno` (dead-letter manual — Storage Queue no trae DLQ nativa, a diferencia de Service Bus) y se registra para revisión. Justificación: evita que un mensaje corrupto bloquee el flujo indefinidamente.
- *La cola crece más rápido de lo que se vacía:* es el comportamiento deseado — la cola **absorbe la ráfaga** (hasta 500 TB) y el productor nunca se bloquea; la señal operativa es monitorear `ApproximateMessagesCount` y, en semana 3, escalar consumidores cuando supere un umbral.

**Estrategia de idempotencia (entregable 23):** el punto seguro para confirmar al cliente es **después de persistir** la transacción cruda (paso 3 de la secuencia): si se confirma antes y la escritura falla, se acusó una transacción que no existe. Ante recepción duplicada del mismo `transaction_id`, la API vuelve a escribir el blob `id.json` con contenido idéntico (sobrescritura de efecto neto nulo) y responde el mismo 202 — el cliente puede reintentar sin generar duplicados. Implementación ya incluida en `storage.persistir_transaccion`.

## Paso 10 — Cierre de jornada y crédito (Entregables 5, 24)

Cada día al terminar:

```bash
bash infra/shutdown.sh        # borra webapp+plan (el gasto de cómputo va a cero)
```

Y consulta el consumo: Portal → **Cost Management → Análisis de costos** (pantallazo diario para tu reporte). Proyección a 3 semanas para el entregable 24: semana 1 ≈ 3–5 USD (B1 con apagado nocturno + centavos de storage); semanas 2–3 suman Azure SQL serverless con auto-pausa (~2–4 USD), Cosmos DB free tier (0 USD), Service Bus Basic (~0.05 USD/millón) y Document Intelligence F0 (0 USD) → total proyectado **15–25 USD de 100–200 disponibles**.

## Paso 11 — Validación de cierre de la semana

Ejecuta la secuencia del documento en orden y registra cada resultado: `shutdown.sh --full` → esperar el borrado → `provision.sh` sobre la suscripción vacía → desplegar API siguiendo solo el README → transacción válida (202) → inválida (400) → documento (201) → cola put/get → intento de acceso al storage desde internet (403) → consultar crédito → `shutdown.sh`. Si algún paso requiere algo no documentado, esa es tu lista de pendientes.

---

## Si el daily es HOY y no tienes nada: plan mínimo de evidencias (60–90 min)

1. Activar suscripción (paso 0) — pantallazo del límite de gasto. *(15 min)*
2. Presupuesto con 3 alertas (paso 1) — pantallazo. *(5 min)*
3. Cloud Shell: los 3 comandos del informe de cuotas (paso 2) — salida copiada. *(10 min)*
4. `bash provision.sh` (paso 5) — salida del script + pantallazo del grupo de recursos con VNet, NSGs, storage y webapp. *(10 min)*
5. Desplegar la API y correr el curl válido + 2 inválidos (paso 6). *(20 min)*
6. Abrir la URL del blob en el navegador → 403 (paso 7). *(2 min)*
7. `bash shutdown.sh` y pantallazo de costos del día. *(5 min)*

Con eso muestras en el daily: suscripción controlada, IaC funcionando, red con aislamiento demostrado, API validando el contrato, e higiene de costos — que es exactamente el espíritu de los 4 temas de la semana.
