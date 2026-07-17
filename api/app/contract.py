"""
Contrato de la transacción — Centinela (entregable 15).

Las cuatro decisiones explícitas del requisito 2.8:

1. MARCA DE TIEMPO: `occurred_at` viaja en UTC (ISO 8601 con zona). El servidor
   añade además `received_at` (generado por la API, no por el cliente). La regla
   de velocidad de la Semana 2 usará `received_at`: el cliente no puede
   manipularla. Se rechazan marcas futuras (> ahora + 120 s de tolerancia de reloj).

2. MONTO: entero en unidades menores (centavos) + código de moneda ISO 4217.
   Nunca punto flotante: 0.1 + 0.2 != 0.3 en IEEE-754, inaceptable en dinero.

3. UBICACIÓN: latitud/longitud decimales (WGS-84). Permite Haversine para la
   regla geo-imposible. Rango validado: lat [-90, 90], lon [-180, 180].

4. IDENTIFICADOR: `transaction_id` UUID generado por el CLIENTE (el emisor de la
   transacción), lo que habilita idempotencia: si llega dos veces el mismo id,
   la API responde el mismo acuse sin duplicar la persistencia (blob con el
   mismo nombre se sobreescribe con contenido idéntico => efecto neto nulo).

Campos no contemplados: política = RECHAZO (extra="forbid"). Un campo
desconocido puede ser un error del emisor o un intento de inyección; en un
sistema financiero se prefiere fallar explícito.
"""
from datetime import datetime, timezone, timedelta
from pydantic import BaseModel, Field, field_validator
import uuid

MONEDAS = {"COP", "USD", "EUR"}
MAX_MONTO_CENTAVOS = 50_000_000_000  # tope "razonable": 500 millones COP en centavos


class Ubicacion(BaseModel):
    model_config = {"extra": "forbid"}
    lat: float = Field(ge=-90, le=90)
    lon: float = Field(ge=-180, le=180)


class Transaccion(BaseModel):
    model_config = {"extra": "forbid"}

    transaction_id: uuid.UUID                    # decisión 4
    account_id: str = Field(min_length=4, max_length=64)   # ¿de qué cuenta?
    amount_minor: int = Field(gt=0, le=MAX_MONTO_CENTAVOS)  # decisión 2: ¿cuál es el monto?
    currency: str                                # ISO 4217
    occurred_at: datetime                        # decisión 1: ¿en qué instante?
    location: Ubicacion                          # decisión 3: ¿desde dónde?
    merchant_id: str = Field(min_length=1, max_length=64)   # ¿hacia qué comercio?
    merchant_category: str = Field(min_length=1, max_length=32)

    @field_validator("currency")
    @classmethod
    def moneda_valida(cls, v: str) -> str:
        if v not in MONEDAS:
            raise ValueError("moneda no soportada")
        return v

    @field_validator("occurred_at")
    @classmethod
    def sin_marcas_futuras(cls, v: datetime) -> datetime:
        if v.tzinfo is None:
            raise ValueError("la marca de tiempo debe incluir zona horaria")
        if v > datetime.now(timezone.utc) + timedelta(seconds=120):
            raise ValueError("marca de tiempo futura")
        return v.astimezone(timezone.utc)
