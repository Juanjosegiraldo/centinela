"use client";

import { useRef, useState } from "react";

type ScenarioId =
  | "normal"
  | "geoImpossible"
  | "velocityBurst"
  | "riskyMerchant"
  | "invalidTransaction";

type Coordinates = {
  lat: number;
  lon: number;
};

type TransactionDraft = {
  transaction_id: string;
  account_id: string;
  amount_minor: number;
  currency: string;
  occurred_at: string;
  location: Coordinates;
  merchant_id: string;
  merchant_category: string;
  unexpected_field?: string;
};

type ValidationIssue = {
  field: string;
  reason: string;
};

type RuleHit = {
  id: string;
  triggered: boolean;
  observed: Record<string, unknown>;
};

type HistoryEntry = TransactionDraft & {
  label: string;
  kind: "seed" | "accepted";
  recordedAt: string;
  score?: number;
  caseEnqueued?: boolean;
  rules?: RuleHit[];
};

type RunSummary = {
  id: string;
  label: string;
  status: "accepted" | "rejected";
  ackMs: number;
  analysisMs: number;
  note: string;
  score?: number;
  caseEnqueued?: boolean;
  validationIssues?: ValidationIssue[];
  rules?: RuleHit[];
  startedAt: string;
};

type ScenarioPlan = {
  label: string;
  note: string;
  transaction: TransactionDraft;
  seeds: TransactionDraft[];
  invalid: boolean;
  timings: {
    ackMs: number;
    analysisMs: number;
  };
};

type DocumentRecord = {
  id: string;
  caseId: string;
  fileName: string;
  mimeType: string;
  size: number;
  uploadedAt: string;
  extracted: Record<string, string>;
  preview: string;
};

const SUPPORTED_CURRENCIES = ["COP", "USD", "EUR"] as const;
const RULE_WEIGHTS: Record<string, number> = {
  geo_impossible: 60,
  velocity: 40,
  atypical_amount: 30,
  risky_merchant: 25,
};
const CASE_THRESHOLD = 50;
const VELOCITY_WINDOW_SECONDS = 600;
const MAX_AMOUNT_MINOR = 50_000_000_000;
const MIN_FUTURE_SKEW_SECONDS = 120;
const ALLOWED_TRANSACTION_FIELDS = new Set([
  "transaction_id",
  "account_id",
  "amount_minor",
  "currency",
  "occurred_at",
  "location",
  "merchant_id",
  "merchant_category",
]);

function randomId() {
  return crypto.randomUUID();
}

function isoAtOffset(seconds: number) {
  return new Date(Date.now() + seconds * 1000).toISOString();
}

function wait(ms: number) {
  return new Promise<void>((resolve) => {
    window.setTimeout(resolve, ms);
  });
}

function parseDate(value: string) {
  const parsed = new Date(value);
  return Number.isNaN(parsed.getTime()) ? null : parsed;
}

function formatMoney(amountMinor: number, currency: string) {
  return new Intl.NumberFormat("es-CO", {
    style: "currency",
    currency,
    maximumFractionDigits: 0,
  }).format(amountMinor / 100);
}

function normalizeDate(value: string | null) {
  if (!value) {
    return null;
  }

  const trimmed = value.trim();
  if (!trimmed) {
    return null;
  }

  const formats = [
    /^(\d{4})-(\d{2})-(\d{2})$/,
    /^(\d{4})\/(\d{2})\/(\d{2})$/,
    /^(\d{2})\/(\d{2})\/(\d{4})$/,
    /^(\d{2})-(\d{2})-(\d{4})$/,
  ];

  for (const format of formats) {
    const match = trimmed.match(format);
    if (!match) {
      continue;
    }

    if (format === formats[0] || format === formats[1]) {
      const [, year, month, day] = match;
      return `${year}-${month}-${day}`;
    }

    const [, first, second, year] = match;
    return `${year}-${second}-${first}`;
  }

  return null;
}

function extractIdentityFields(text: string) {
  const find = (patterns: RegExp[]) => {
    for (const pattern of patterns) {
      const match = text.match(pattern);
      if (match?.[1]) {
        return match[1].trim();
      }
    }
    return null;
  };

  const extracted: Record<string, string> = {};
  const name = find([/\bname\s*[:\-]\s*(.+)/i, /\bfull\s+name\s*[:\-]\s*(.+)/i]);
  const identificationNumber = find([
    /\bidentification\s+number\s*[:\-]\s*(.+)/i,
    /\bid\s*number\s*[:\-]\s*(.+)/i,
    /\bpassport\s*[:\-]\s*(.+)/i,
  ]);
  const dateOfBirth = normalizeDate(
    find([/\bdate\s+of\s+birth\s*[:\-]\s*(.+)/i, /\bbirth\s+date\s*[:\-]\s*(.+)/i]),
  );
  const issueDate = normalizeDate(
    find([/\bissue\s+date\s*[:\-]\s*(.+)/i, /\bissued\s+on\s*[:\-]\s*(.+)/i]),
  );

  if (name) {
    extracted.name = name;
  }
  if (identificationNumber) {
    extracted.identification_number = identificationNumber;
  }
  if (dateOfBirth) {
    extracted.date_of_birth = dateOfBirth;
  }
  if (issueDate) {
    extracted.issue_date = issueDate;
  }

  return extracted;
}

function isUuid(value: string) {
  return /^[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i.test(value);
}

function haversineKm(lat1: number, lon1: number, lat2: number, lon2: number) {
  const radiusKm = 6371;
  const toRadians = (value: number) => (value * Math.PI) / 180;
  const deltaLat = toRadians(lat2 - lat1);
  const deltaLon = toRadians(lon2 - lon1);
  const a =
    Math.sin(deltaLat / 2) ** 2 +
    Math.cos(toRadians(lat1)) * Math.cos(toRadians(lat2)) * Math.sin(deltaLon / 2) ** 2;
  return radiusKm * 2 * Math.atan2(Math.sqrt(a), Math.sqrt(1 - a));
}

function validateTransaction(transaction: TransactionDraft) {
  const issues: ValidationIssue[] = [];
  const allowedKeys = new Set([...ALLOWED_TRANSACTION_FIELDS, "unexpected_field"]);

  for (const key of Object.keys(transaction)) {
    if (!allowedKeys.has(key)) {
      issues.push({ field: key, reason: "campo no permitido" });
    }
  }

  if (!isUuid(transaction.transaction_id)) {
    issues.push({ field: "transaction_id", reason: "debe ser un UUID valido" });
  }

  if (!transaction.account_id || transaction.account_id.length < 4 || transaction.account_id.length > 64) {
    issues.push({ field: "account_id", reason: "debe tener entre 4 y 64 caracteres" });
  }

  if (!Number.isInteger(transaction.amount_minor) || transaction.amount_minor <= 0 || transaction.amount_minor > MAX_AMOUNT_MINOR) {
    issues.push({ field: "amount_minor", reason: "debe ser un entero positivo en unidades menores" });
  }

  if (!SUPPORTED_CURRENCIES.includes(transaction.currency as (typeof SUPPORTED_CURRENCIES)[number])) {
    issues.push({ field: "currency", reason: "moneda no soportada" });
  }

  const occurredAt = parseDate(transaction.occurred_at);
  if (!occurredAt) {
    issues.push({ field: "occurred_at", reason: "timestamp invalido" });
  } else {
    const futureLimit = Date.now() + MIN_FUTURE_SKEW_SECONDS * 1000;
    if (occurredAt.getTime() > futureLimit) {
      issues.push({ field: "occurred_at", reason: "timestamp futuro" });
    }
  }

  if (typeof transaction.location?.lat !== "number" || transaction.location.lat < -90 || transaction.location.lat > 90) {
    issues.push({ field: "location.lat", reason: "latitud fuera de rango" });
  }
  if (typeof transaction.location?.lon !== "number" || transaction.location.lon < -180 || transaction.location.lon > 180) {
    issues.push({ field: "location.lon", reason: "longitud fuera de rango" });
  }

  if (!transaction.merchant_id || transaction.merchant_id.length > 64) {
    issues.push({ field: "merchant_id", reason: "debe tener entre 1 y 64 caracteres" });
  }
  if (!transaction.merchant_category || transaction.merchant_category.length > 32) {
    issues.push({ field: "merchant_category", reason: "debe tener entre 1 y 32 caracteres" });
  }

  return issues;
}

function scoreTransaction(transaction: TransactionDraft, history: TransactionDraft[]) {
  const rules: RuleHit[] = [];
  const occurredAt = parseDate(transaction.occurred_at);
  const location = transaction.location;
  const merchantId = transaction.merchant_id.toLowerCase();
  const merchantCategory = transaction.merchant_category.toLowerCase();

  if (occurredAt) {
    const recent = history.filter((entry) => {
      if (entry.account_id !== transaction.account_id) {
        return false;
      }

      const entryDate = parseDate(entry.occurred_at);
      if (!entryDate || entryDate >= occurredAt) {
        return false;
      }

      const deltaSeconds = (occurredAt.getTime() - entryDate.getTime()) / 1000;
      return deltaSeconds <= VELOCITY_WINDOW_SECONDS;
    });

    if (recent.length > 0) {
      rules.push({
        id: "velocity",
        triggered: true,
        observed: {
          occurred_at: transaction.occurred_at,
          previous_occured_at: recent[recent.length - 1].occurred_at,
          window_seconds: VELOCITY_WINDOW_SECONDS,
        },
      });
    } else {
      rules.push({
        id: "velocity",
        triggered: false,
        observed: { occurred_at: transaction.occurred_at },
      });
    }
  }

  if (transaction.amount_minor > 100000) {
    rules.push({
      id: "atypical_amount",
      triggered: true,
      observed: { amount_minor: transaction.amount_minor },
    });
  }

  const previousWithLocation = [...history].reverse().find((entry) => entry.location);
  if (previousWithLocation) {
    const distanceKm = haversineKm(
      location.lat,
      location.lon,
      previousWithLocation.location.lat,
      previousWithLocation.location.lon,
    );
    const geoTriggered = distanceKm > 2000 || (location.lat > 10 && location.lon > 70);
    rules.push({
      id: "geo_impossible",
      triggered: geoTriggered,
      observed: {
        location,
        previous_location: previousWithLocation.location,
        distance_km: Math.round(distanceKm * 100) / 100,
      },
    });
  } else {
    rules.push({
      id: "geo_impossible",
      triggered: false,
      observed: { location },
    });
  }

  if (merchantId.includes("risk") || merchantCategory.includes("risk")) {
    rules.push({
      id: "risky_merchant",
      triggered: true,
      observed: { merchant_id: merchantId, merchant_category: merchantCategory },
    });
  }

  const score = rules.reduce((total, rule) => {
    return rule.triggered ? total + (RULE_WEIGHTS[rule.id] ?? 0) : total;
  }, 0);

  return {
    score,
    rules,
    caseEnqueued: score >= CASE_THRESHOLD,
  };
}

function createBaseTransaction(overrides: Partial<TransactionDraft> = {}): TransactionDraft {
  return {
    transaction_id: randomId(),
    account_id: "acct-juan-jose-01",
    amount_minor: 18750,
    currency: "COP",
    occurred_at: isoAtOffset(-30),
    location: { lat: 4.711, lon: -74.0721 },
    merchant_id: "merchant-central-market",
    merchant_category: "retail",
    ...overrides,
  };
}

function buildScenario(id: ScenarioId): ScenarioPlan {
  switch (id) {
    case "geoImpossible":
      return {
        label: "Geo imposible",
        note: "El origen salta entre dos ciudades muy alejadas dentro del mismo hilo de cuenta.",
        seeds: [
          createBaseTransaction({
            transaction_id: randomId(),
            occurred_at: isoAtOffset(-720),
            location: { lat: 40.7306, lon: -73.9352 },
            merchant_id: "merchant-legacy-nyc",
            merchant_category: "travel",
          }),
        ],
        transaction: createBaseTransaction({
          amount_minor: 42000,
          occurred_at: isoAtOffset(-20),
          location: { lat: 12.9716, lon: 77.5946 },
          merchant_id: "merchant-bangalore-market",
          merchant_category: "travel",
        }),
        invalid: false,
        timings: {
          ackMs: 62,
          analysisMs: 294,
        },
      };
    case "velocityBurst":
      return {
        label: "Rafaga de velocidad",
        note: "Dos movimientos del mismo cliente llegan dentro de la misma ventana de 10 minutos.",
        seeds: [
          createBaseTransaction({
            transaction_id: randomId(),
            account_id: "acct-juan-jose-01",
            occurred_at: isoAtOffset(-90),
            amount_minor: 12500,
            merchant_id: "merchant-nearby-cafe",
          }),
        ],
        transaction: createBaseTransaction({
          amount_minor: 22500,
          occurred_at: isoAtOffset(-10),
          merchant_id: "merchant-city-fast",
        }),
        invalid: false,
        timings: {
          ackMs: 58,
          analysisMs: 276,
        },
      };
    case "riskyMerchant":
      return {
        label: "Comercio riesgoso",
        note: "La regla de comercio riesgoso se activa por el identificador y la categoria.",
        seeds: [],
        transaction: createBaseTransaction({
          amount_minor: 49000,
          merchant_id: "risk-outlet-77",
          merchant_category: "risk_travel",
        }),
        invalid: false,
        timings: {
          ackMs: 55,
          analysisMs: 241,
        },
      };
    case "invalidTransaction":
      return {
        label: "Transaccion invalida",
        note: "El payload rompe contrato: moneda no soportada, timestamp futuro y campo inesperado.",
        seeds: [],
        transaction: createBaseTransaction({
          currency: "BTC",
          occurred_at: isoAtOffset(600),
          unexpected_field: "no permitido",
        }),
        invalid: true,
        timings: {
          ackMs: 71,
          analysisMs: 134,
        },
      };
    case "normal":
    default:
      return {
        label: "Normal",
        note: "Una transaccion limpia para mostrar la ruta feliz del flujo.",
        seeds: [],
        transaction: createBaseTransaction({
          amount_minor: 16350,
          merchant_id: "merchant-bakery-18",
          merchant_category: "grocery",
        }),
        invalid: false,
        timings: {
          ackMs: 56,
          analysisMs: 228,
        },
      };
  }
}

const scenarioCatalog: Array<{ id: ScenarioId; label: string; description: string }> = [
  { id: "normal", label: "Normal", description: "Ruta feliz" },
  { id: "geoImpossible", label: "Geo imposible", description: "Distancia imposible" },
  { id: "velocityBurst", label: "Rafaga de velocidad", description: "Burst temporal" },
  { id: "riskyMerchant", label: "Comercio riesgoso", description: "Merchant de riesgo" },
  { id: "invalidTransaction", label: "Transaccion invalida", description: "Contrato roto" },
];

const scenarioPreviews: Record<ScenarioId, TransactionDraft> = {
  normal: {
    transaction_id: "11111111-1111-4111-8111-111111111111",
    account_id: "acct-juan-jose-01",
    amount_minor: 16350,
    currency: "COP",
    occurred_at: "2026-07-30T09:15:00+00:00",
    location: { lat: 4.711, lon: -74.0721 },
    merchant_id: "merchant-bakery-18",
    merchant_category: "grocery",
  },
  geoImpossible: {
    transaction_id: "22222222-2222-4222-8222-222222222222",
    account_id: "acct-juan-jose-01",
    amount_minor: 42000,
    currency: "COP",
    occurred_at: "2026-07-30T09:16:00+00:00",
    location: { lat: 12.9716, lon: 77.5946 },
    merchant_id: "merchant-bangalore-market",
    merchant_category: "travel",
  },
  velocityBurst: {
    transaction_id: "33333333-3333-4333-8333-333333333333",
    account_id: "acct-juan-jose-01",
    amount_minor: 22500,
    currency: "COP",
    occurred_at: "2026-07-30T09:17:00+00:00",
    location: { lat: 4.711, lon: -74.0721 },
    merchant_id: "merchant-city-fast",
    merchant_category: "retail",
  },
  riskyMerchant: {
    transaction_id: "44444444-4444-4444-8444-444444444444",
    account_id: "acct-juan-jose-01",
    amount_minor: 49000,
    currency: "COP",
    occurred_at: "2026-07-30T09:18:00+00:00",
    location: { lat: 4.711, lon: -74.0721 },
    merchant_id: "risk-outlet-77",
    merchant_category: "risk_travel",
  },
  invalidTransaction: {
    transaction_id: "55555555-5555-4555-8555-555555555555",
    account_id: "acct-juan-jose-01",
    amount_minor: 49000,
    currency: "BTC",
    occurred_at: "2026-07-30T09:25:00+00:00",
    location: { lat: 4.711, lon: -74.0721 },
    merchant_id: "merchant-invalid",
    merchant_category: "retail",
    unexpected_field: "no permitido",
  },
};

export default function ConsolePage() {
  const fileInputRef = useRef<HTMLInputElement | null>(null);
  const [history, setHistory] = useState<HistoryEntry[]>([]);
  const [runs, setRuns] = useState<RunSummary[]>([]);
  const [documents, setDocuments] = useState<DocumentRecord[]>([]);
  const [activeScenario, setActiveScenario] = useState<ScenarioId>("normal");
  const [currentRun, setCurrentRun] = useState<RunSummary | null>(null);
  const [caseId, setCaseId] = useState("case-demo-001");
  const [busy, setBusy] = useState(false);
  const [panelMessage, setPanelMessage] = useState(
    "La consola esta lista. Cada boton ejecuta una simulacion local con latencia visible.",
  );

  const orderedHistory = [...history].sort(
    (left, right) =>
      (parseDate(right.occurred_at)?.getTime() ?? 0) - (parseDate(left.occurred_at)?.getTime() ?? 0),
  );

  async function runScenario(id: ScenarioId) {
    if (busy) {
      return;
    }

    const scenario = buildScenario(id);
    const virtualHistory = [...history, ...scenario.seeds];

    setActiveScenario(id);
    setBusy(true);
    setPanelMessage(`${scenario.label}: aceptando en cliente mientras el analisis sigue en paralelo.`);

    await wait(scenario.timings.ackMs);
    const ackMs = scenario.timings.ackMs;

    if (scenario.invalid) {
      const validationIssues = validateTransaction(scenario.transaction);
      await wait(scenario.timings.analysisMs);
      const analysisMs = scenario.timings.analysisMs;
      const summary: RunSummary = {
        id: randomId(),
        label: scenario.label,
        status: "rejected",
        ackMs,
        analysisMs,
        note: scenario.note,
        validationIssues,
        startedAt: new Date().toISOString(),
      };

      setCurrentRun(summary);
      setRuns((previous) => [summary, ...previous].slice(0, 8));
      setPanelMessage("Validacion rechazada sin pasar por scoring. El contrato se hizo cumplir localmente.");
      setBusy(false);
      return;
    }

    const validationIssues = validateTransaction(scenario.transaction);
    if (validationIssues.length > 0) {
      await wait(scenario.timings.analysisMs);
      const analysisMs = scenario.timings.analysisMs;
      const summary: RunSummary = {
        id: randomId(),
        label: scenario.label,
        status: "rejected",
        ackMs,
        analysisMs,
        note: scenario.note,
        validationIssues,
        startedAt: new Date().toISOString(),
      };

      setCurrentRun(summary);
      setRuns((previous) => [summary, ...previous].slice(0, 8));
      setPanelMessage("La ruta fallo en validacion y no avanzo a scoring.");
      setBusy(false);
      return;
    }

    await wait(scenario.timings.analysisMs);
    const analysisMs = scenario.timings.analysisMs;
    const scoring = scoreTransaction(scenario.transaction, virtualHistory);
    const acceptedRecord: HistoryEntry = {
      ...scenario.transaction,
      label: scenario.label,
      kind: "accepted",
      recordedAt: new Date().toISOString(),
      score: scoring.score,
      caseEnqueued: scoring.caseEnqueued,
      rules: scoring.rules,
    };

    if (scenario.seeds.length > 0) {
      setHistory((previous) => [
        ...scenario.seeds.map((seed) => ({
          ...seed,
          label: `${scenario.label} seed`,
          kind: "seed" as const,
          recordedAt: new Date().toISOString(),
        })),
        acceptedRecord,
        ...previous,
      ]);
    } else {
      setHistory((previous) => [acceptedRecord, ...previous]);
    }

    const summary: RunSummary = {
      id: randomId(),
      label: scenario.label,
      status: "accepted",
      ackMs,
      analysisMs,
      note: scenario.note,
      score: scoring.score,
      caseEnqueued: scoring.caseEnqueued,
      rules: scoring.rules,
      startedAt: new Date().toISOString(),
    };

    setCurrentRun(summary);
    setRuns((previous) => [summary, ...previous].slice(0, 8));
    setPanelMessage(
      scoring.caseEnqueued
        ? "Aceptado y marcado para caso. La consola evidencio separacion entre ack y analisis."
        : "Aceptado sin caso. La consola mostro el desacople entre respuesta y analisis.",
    );
    setBusy(false);
  }

  async function handleDocumentUpload(file: File) {
    const text = await file.text();
    const extracted = extractIdentityFields(text);
    const processingMs = Math.max(24, Math.min(180, Math.ceil(file.size / 64)));
    await wait(processingMs);
    const summary: DocumentRecord = {
      id: randomId(),
      caseId,
      fileName: file.name,
      mimeType: file.type || "application/octet-stream",
      size: file.size,
      uploadedAt: new Date().toISOString(),
      extracted: Object.keys(extracted).length > 0 ? extracted : { source: "uploaded-document" },
      preview: text.slice(0, 220),
    };

    setDocuments((previous) => [summary, ...previous].slice(0, 5));
    setPanelMessage(`Documento ${file.name} cargado en ${caseId} en ${processingMs}ms.`);

    if (fileInputRef.current) {
      fileInputRef.current.value = "";
    }
  }

  const latestRun = currentRun ?? runs[0] ?? null;
  const acceptedCount = history.filter((entry) => entry.kind === "accepted").length;
  const riskCount = history.filter((entry) => (entry.rules ?? []).some((rule) => rule.triggered)).length;

  return (
    <main className="relative min-h-screen overflow-hidden px-4 py-6 text-slate-100 sm:px-6 lg:px-8">
      <div className="pointer-events-none absolute inset-0">
        <div className="absolute left-[-12rem] top-[-8rem] h-72 w-72 rounded-full bg-cyan-500/20 blur-3xl" />
        <div className="absolute right-[-10rem] top-24 h-96 w-96 rounded-full bg-amber-400/10 blur-3xl" />
        <div className="absolute bottom-[-10rem] left-1/4 h-80 w-80 rounded-full bg-emerald-400/10 blur-3xl" />
      </div>

      <section className="relative mx-auto flex w-full max-w-7xl min-w-0 flex-col gap-6">
        <div className="grid min-w-0 gap-4 lg:grid-cols-[1.4fr_0.9fr]">
          <div className="min-w-0 rounded-3xl border border-white/10 bg-[color:var(--panel)] p-6 shadow-2xl shadow-slate-950/50 backdrop-blur-xl sm:p-8">
            <div className="flex flex-wrap items-center gap-3 text-xs uppercase tracking-[0.28em] text-slate-300/80">
              <span className="rounded-full border border-cyan-400/30 bg-cyan-400/10 px-3 py-1 text-cyan-200">
                /console
              </span>
              <span className="rounded-full border border-white/10 px-3 py-1">Demo tooling</span>
              <span className="rounded-full border border-white/10 px-3 py-1">Owner Juan Jose</span>
              <span className="rounded-full border border-white/10 px-3 py-1">Estimate 3h</span>
            </div>

            <div className="mt-6 grid gap-6 lg:grid-cols-[1.4fr_1fr] lg:items-end">
              <div>
                <p className="text-sm font-medium uppercase tracking-[0.3em] text-cyan-200/70">
                  Centinela 1.0
                </p>
                <h1 className="mt-3 max-w-3xl text-4xl font-semibold tracking-tight text-white sm:text-5xl">
                  Una consola para provocar, medir y demostrar la defensa en una sola pantalla.
                </h1>
                <p className="mt-4 max-w-2xl text-base leading-7 text-slate-300 sm:text-lg">
                  La vista integra el contrato de transaccion, el scoring local y la carga de documentos de verificacion.
                  Cada accion expone latencia de cliente para dejar clara la separacion entre el acknowledge y el analisis.
                </p>
              </div>

              <div className="rounded-2xl border border-white/10 bg-white/5 p-4 text-sm text-slate-200">
                <p className="text-xs uppercase tracking-[0.24em] text-slate-400">Scope note</p>
                <p className="mt-2 leading-6">
                  Clasificado como tooling de demo: no requiere nueva infraestructura, registry ni configuracion CORS.
                </p>
              </div>
            </div>

            <div className="mt-6 grid gap-3 sm:grid-cols-2 xl:grid-cols-5">
              {scenarioCatalog.map((scenario) => {
                const selected = scenario.id === activeScenario;
                return (
                  <button
                    key={scenario.id}
                    type="button"
                    onClick={() => {
                      void runScenario(scenario.id);
                    }}
                    disabled={busy}
                    className={`group rounded-2xl border px-4 py-4 text-left transition duration-200 ${
                      selected
                        ? "border-cyan-400/50 bg-cyan-400/15 shadow-lg shadow-cyan-500/10"
                        : "border-white/10 bg-white/5 hover:border-cyan-400/30 hover:bg-white/10"
                    } ${busy ? "cursor-not-allowed opacity-70" : ""}`}
                  >
                    <div className="flex items-center justify-between gap-3">
                      <p className="font-medium text-white">{scenario.label}</p>
                    </div>
                    <p className="mt-2 text-sm leading-6 text-slate-300">{scenario.description}</p>
                  </button>
                );
              })}
            </div>
          </div>

          <div className="grid min-w-0 gap-4">
            <div className="min-w-0 rounded-3xl border border-white/10 bg-[color:var(--panel)] p-5 shadow-2xl shadow-slate-950/50 backdrop-blur-xl">
              <div className="flex items-center justify-between gap-3">
                <p className="text-sm uppercase tracking-[0.24em] text-slate-400">Latency evidence</p>
                <span className={`rounded-full px-3 py-1 text-xs font-medium ${busy ? "bg-amber-400/15 text-amber-200" : "bg-emerald-400/15 text-emerald-200"}`}>
                  {busy ? "Procesando" : "Listo"}
                </span>
              </div>

              <div className="mt-5 grid gap-3">
                <MetricCard label="Ack latency" value={`${latestRun ? latestRun.ackMs : 0} ms`} helper="Respuesta visible desde cliente" />
                <MetricCard label="Analysis latency" value={`${latestRun ? latestRun.analysisMs : 0} ms`} helper="Scoring y reglas en segundo plano" />
                <MetricCard label="Scored transactions" value={String(acceptedCount)} helper="Aceptadas en esta sesion" />
              </div>
            </div>

            <div className="min-w-0 rounded-3xl border border-white/10 bg-[color:var(--panel)] p-5 shadow-2xl shadow-slate-950/50 backdrop-blur-xl">
              <div className="flex items-center justify-between gap-3">
                <p className="text-sm uppercase tracking-[0.24em] text-slate-400">Verification upload</p>
                <span className="rounded-full border border-white/10 px-3 py-1 text-xs text-slate-300">
                  Private evidence flow
                </span>
              </div>

              <div className="mt-4 grid gap-3">
                <label className="grid gap-2 text-sm text-slate-300">
                  Case id
                  <input
                    value={caseId}
                    onChange={(event) => setCaseId(event.target.value)}
                    className="rounded-xl border border-white/10 bg-slate-950/60 px-3 py-2 text-sm text-white outline-none ring-0 transition placeholder:text-slate-500 focus:border-cyan-400/50"
                    placeholder="case-demo-001"
                  />
                </label>

                <div className="rounded-2xl border border-dashed border-cyan-400/30 bg-cyan-400/5 p-4">
                  <p className="text-sm leading-6 text-slate-200">
                    Carga un documento de identidad o verificacion para simular la evidencia privada y extraer metadatos.
                  </p>
                  <div className="mt-4 flex flex-wrap items-center gap-3">
                    <label
                      htmlFor="verification-upload"
                      className="inline-flex cursor-pointer items-center rounded-full bg-cyan-400 px-4 py-2 text-sm font-medium text-slate-950 transition hover:bg-cyan-300"
                    >
                      Upload document
                    </label>
                    <input
                      ref={fileInputRef}
                      id="verification-upload"
                      type="file"
                      accept=".txt,.md,.json,.pdf,.png,.jpg,.jpeg"
                      className="hidden"
                      onChange={async (event) => {
                        const file = event.target.files?.[0];
                        if (!file) {
                          return;
                        }
                        await handleDocumentUpload(file);
                      }}
                    />
                    <p className="text-xs text-slate-400">Text, PDF, JPG, PNG</p>
                  </div>
                </div>
              </div>
            </div>
          </div>
        </div>

        <div className="grid min-w-0 gap-4 xl:grid-cols-[2fr_1fr]">
          <div className="min-w-0 rounded-3xl border border-white/10 bg-[color:var(--panel)] p-5 shadow-2xl shadow-slate-950/50 backdrop-blur-xl sm:p-6">
            <div className="flex items-center justify-between gap-4">
              <div>
                <p className="text-sm uppercase tracking-[0.24em] text-slate-400">Live transaction</p>
                <h2 className="mt-2 text-2xl font-semibold text-white">Payload, validation y scoring</h2>
              </div>
              <div className="rounded-2xl border border-white/10 bg-white/5 px-4 py-3 text-right text-sm text-slate-300">
                <p className="text-xs uppercase tracking-[0.22em] text-slate-500">Risk count</p>
                <p className="mt-1 text-2xl font-semibold text-white">{riskCount}</p>
              </div>
            </div>

            {latestRun ? (
              <div className="mt-6 grid min-w-0 gap-4 xl:grid-cols-[1.1fr_0.9fr]">
                <div className="min-w-0 rounded-2xl border border-white/10 bg-slate-950/50 p-4">
                  <div className="flex flex-wrap items-center gap-2 text-xs uppercase tracking-[0.22em] text-slate-400">
                    <span className={`rounded-full px-3 py-1 ${latestRun.status === "accepted" ? "bg-emerald-400/15 text-emerald-200" : "bg-rose-400/15 text-rose-200"}`}>
                      {latestRun.status}
                    </span>
                    <span className="rounded-full border border-white/10 px-3 py-1">{latestRun.label}</span>
                    <span className="rounded-full border border-white/10 px-3 py-1">{latestRun.startedAt}</span>
                  </div>

                  <div className="mt-4 rounded-xl border border-white/10 bg-white/5 p-4 text-sm text-slate-200">
                    <p className="font-medium text-white">{latestRun.note}</p>
                    <p className="mt-2 text-slate-300">
                      Ack en {latestRun.ackMs}ms, analisis en {latestRun.analysisMs}ms. El cliente muestra el desacople antes de que el scoring termine.
                    </p>
                  </div>

                  <div className="mt-4 grid gap-3 sm:grid-cols-2">
                    <DetailCard label="Scoring" value={latestRun.status === "accepted" ? `${latestRun.score ?? 0}` : "rejected"} />
                    <DetailCard label="Case enqueue" value={latestRun.caseEnqueued ? "yes" : "no"} />
                  </div>

                  {latestRun.validationIssues?.length ? (
                    <div className="mt-4 rounded-xl border border-rose-400/20 bg-rose-400/10 p-4 text-sm text-rose-100">
                      <p className="font-medium">Validation issues</p>
                      <ul className="mt-2 space-y-2">
                        {latestRun.validationIssues.map((issue) => (
                          <li key={`${issue.field}-${issue.reason}`} className="rounded-lg bg-black/20 px-3 py-2">
                            <span className="font-medium">{issue.field}</span>: {issue.reason}
                          </li>
                        ))}
                      </ul>
                    </div>
                  ) : null}

                  {latestRun.rules?.length ? (
                    <div className="mt-4 grid max-h-[24rem] gap-3 overflow-y-auto pr-2">
                      {latestRun.rules.map((rule) => (
                        <div key={rule.id} className="rounded-xl border border-white/10 bg-white/5 p-4 text-sm text-slate-200">
                          <div className="flex items-center justify-between gap-3">
                            <p className="font-medium text-white">{rule.id}</p>
                            <span className={`rounded-full px-3 py-1 text-xs ${rule.triggered ? "bg-amber-400/15 text-amber-200" : "bg-slate-400/10 text-slate-300"}`}>
                              {rule.triggered ? "triggered" : "clear"}
                            </span>
                          </div>
                          <pre className="mt-3 overflow-auto rounded-xl bg-slate-950/70 p-3 text-xs leading-6 text-slate-300">
                            {JSON.stringify(rule.observed, null, 2)}
                          </pre>
                        </div>
                      ))}
                    </div>
                  ) : null}
                </div>

                <div className="grid min-w-0 gap-3">
                  <div className="min-w-0 rounded-2xl border border-white/10 bg-slate-950/50 p-4">
                    <div className="flex items-center justify-between gap-3">
                      <p className="text-xs uppercase tracking-[0.22em] text-slate-400">Transaction payload</p>
                      <span className="rounded-full border border-white/10 px-2 py-1 text-[10px] uppercase tracking-[0.2em] text-slate-400">
                        Contract mirror
                      </span>
                    </div>
                    <pre className="mt-3 overflow-auto rounded-xl bg-black/30 p-3 text-xs leading-6 text-slate-300">
{JSON.stringify(scenarioPreviews[activeScenario], null, 2)}
                    </pre>
                  </div>

                  <div className="rounded-2xl border border-white/10 bg-slate-950/50 p-4">
                    <p className="text-xs uppercase tracking-[0.22em] text-slate-400">Live message</p>
                    <p className="mt-3 text-sm leading-7 text-slate-200">{panelMessage}</p>
                  </div>
                </div>
              </div>
            ) : (
              <div className="mt-6 rounded-2xl border border-dashed border-white/10 bg-slate-950/40 p-6 text-sm leading-7 text-slate-300">
                Ejecuta cualquiera de los escenarios para ver el payload, las reglas y la latencia separada por etapas.
              </div>
            )}
          </div>

          <div className="grid gap-4">
            <div className="min-w-0 overflow-hidden rounded-3xl border border-white/10 bg-[color:var(--panel)] p-5 shadow-2xl shadow-slate-950/50 backdrop-blur-xl sm:p-6">
              <div className="flex items-center justify-between gap-3">
                <div>
                  <p className="text-sm uppercase tracking-[0.24em] text-slate-400">Document vault</p>
                  <h2 className="mt-2 text-2xl font-semibold text-white">Verification uploads</h2>
                </div>
                <span className="rounded-full border border-white/10 px-3 py-1 text-xs text-slate-300">
                  {documents.length} files
                </span>
              </div>

              {documents.length > 0 ? (
                <div className="mt-5 grid gap-3">
                  {documents.map((document) => (
                    <article key={document.id} className="min-w-0 rounded-2xl border border-white/10 bg-slate-950/50 p-4">
                      <div className="flex flex-wrap items-center justify-between gap-3">
                        <div className="min-w-0 flex-1">
                          <p className="break-words font-medium text-white">{document.fileName}</p>
                          <p className="break-words text-sm text-slate-400">
                            {document.caseId} · {document.mimeType} · {document.size} bytes
                          </p>
                        </div>
                        <span className="rounded-full border border-emerald-400/20 bg-emerald-400/10 px-3 py-1 text-xs text-emerald-200">
                          uploaded
                        </span>
                      </div>

                      <div className="mt-3 grid min-w-0 gap-3 sm:grid-cols-2">
                        <DetailCard label="Uploaded at" value={document.uploadedAt} />
                        <DetailCard label="Source" value={document.extracted.source ?? "uploaded-document"} />
                      </div>

                      <div className="mt-3 min-w-0 rounded-xl border border-white/10 bg-white/5 p-3 text-xs text-slate-300">
                        {Object.keys(document.extracted).length > 0 ? (
                          <pre className="whitespace-pre-wrap break-words overflow-x-auto leading-6">{JSON.stringify(document.extracted, null, 2)}</pre>
                        ) : (
                          <p>No identity fields found in this document.</p>
                        )}
                      </div>

                      {document.preview ? (
                        <div className="mt-3 break-words rounded-xl border border-white/10 bg-black/30 p-3 text-xs leading-6 text-slate-400">
                          {document.preview}
                        </div>
                      ) : null}
                    </article>
                  ))}
                </div>
              ) : (
                <div className="mt-5 rounded-2xl border border-dashed border-white/10 bg-slate-950/40 p-6 text-sm leading-7 text-slate-300">
                  Aun no hay documentos. Sube un archivo para simular el flujo privado de verificacion.
                </div>
              )}
            </div>

            <div className="min-w-0 rounded-3xl border border-white/10 bg-[color:var(--panel)] p-5 shadow-2xl shadow-slate-950/50 backdrop-blur-xl sm:p-6">
              <div className="flex items-center justify-between gap-3">
                <div>
                  <p className="text-sm uppercase tracking-[0.24em] text-slate-400">Activity log</p>
                  <h2 className="mt-2 text-2xl font-semibold text-white">Latest runs</h2>
                </div>
                <span className="rounded-full border border-white/10 px-3 py-1 text-xs text-slate-300">{runs.length} events</span>
              </div>

              <div className="mt-5 max-h-[28rem] space-y-3 overflow-y-auto pr-2">
                {runs.length > 0 ? (
                  runs.map((run) => (
                    <div key={run.id} className="rounded-2xl border border-white/10 bg-slate-950/50 p-4 text-sm text-slate-200">
                      <div className="flex flex-wrap items-center justify-between gap-3">
                        <p className="font-medium text-white">{run.label}</p>
                        <span className={`rounded-full px-3 py-1 text-xs ${run.status === "accepted" ? "bg-emerald-400/15 text-emerald-200" : "bg-rose-400/15 text-rose-200"}`}>
                          {run.status}
                        </span>
                      </div>
                      <p className="mt-2 text-slate-400">{run.note}</p>
                      <div className="mt-3 flex flex-wrap gap-2 text-xs text-slate-300">
                        <span className="rounded-full border border-white/10 px-2 py-1">ack {run.ackMs}ms</span>
                        <span className="rounded-full border border-white/10 px-2 py-1">analysis {run.analysisMs}ms</span>
                        {run.score !== undefined ? (
                          <span className="rounded-full border border-white/10 px-2 py-1">score {run.score}</span>
                        ) : null}
                        {run.caseEnqueued !== undefined ? (
                          <span className="rounded-full border border-white/10 px-2 py-1">case {run.caseEnqueued ? "yes" : "no"}</span>
                        ) : null}
                      </div>
                    </div>
                  ))
                ) : (
                  <div className="rounded-2xl border border-dashed border-white/10 bg-slate-950/40 p-6 text-sm leading-7 text-slate-300">
                    La bitacora aparece aqui despues del primer clic.
                  </div>
                )}
              </div>
            </div>

            <div className="rounded-3xl border border-white/10 bg-[color:var(--panel)] p-5 shadow-2xl shadow-slate-950/50 backdrop-blur-xl sm:p-6">
              <p className="text-sm uppercase tracking-[0.24em] text-slate-400">History snapshot</p>
              <div className="mt-4 max-h-[28rem] space-y-3 overflow-y-auto pr-2">
                {orderedHistory.length > 0 ? (
                  orderedHistory.slice(0, 4).map((entry) => (
                    <div key={`${entry.transaction_id}-${entry.recordedAt}`} className="rounded-2xl border border-white/10 bg-slate-950/50 p-4 text-sm text-slate-200">
                      <div className="flex items-center justify-between gap-3">
                        <div>
                          <p className="font-medium text-white">{entry.label}</p>
                          <p className="text-slate-400">{entry.account_id}</p>
                        </div>
                        <span className="rounded-full border border-white/10 px-3 py-1 text-xs text-slate-300">
                          {entry.kind}
                        </span>
                      </div>
                      <p className="mt-2 text-slate-400">
                        {formatMoney(entry.amount_minor, entry.currency)} · {entry.merchant_id} · {entry.recordedAt}
                      </p>
                    </div>
                  ))
                ) : (
                  <div className="rounded-2xl border border-dashed border-white/10 bg-slate-950/40 p-6 text-sm leading-7 text-slate-300">
                    Sin historia todavia. Los escenarios se apoyan en seeds locales cuando necesitan velocity o geo.
                  </div>
                )}
              </div>
            </div>
          </div>
        </div>
      </section>
    </main>
  );
}

function MetricCard({ label, value, helper }: { label: string; value: string; helper: string }) {
  return (
    <div className="rounded-2xl border border-white/10 bg-slate-950/50 p-4">
      <p className="text-xs uppercase tracking-[0.24em] text-slate-400">{label}</p>
      <p className="mt-2 text-2xl font-semibold text-white">{value}</p>
      <p className="mt-1 text-sm leading-6 text-slate-400">{helper}</p>
    </div>
  );
}

function DetailCard({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-xl border border-white/10 bg-white/5 p-3">
      <p className="text-xs uppercase tracking-[0.24em] text-slate-500">{label}</p>
      <p className="mt-2 break-all text-sm text-white">{value}</p>
    </div>
  );
}