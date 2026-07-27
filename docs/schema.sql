-- Centinela — Case store schema (Week 2, Deliverable 3)
-- Relational store: low volume, referential integrity, reporting, traceability.
-- Run against casesdb from inside the app subnet (the server denies public access).

-- Catalogue of possible case states (referenced, not free text)
CREATE TABLE case_states (
    state_id    INT PRIMARY KEY,
    name        VARCHAR(32) NOT NULL UNIQUE,
    is_terminal BIT NOT NULL DEFAULT 0
);

INSERT INTO case_states (state_id, name, is_terminal) VALUES
    (1, 'open',        0),
    (2, 'in_review',   0),
    (3, 'escalated',   0),
    (4, 'confirmed',   1),
    (5, 'dismissed',   1);

-- A case is opened when a transaction's score exceeds the threshold
CREATE TABLE cases (
    case_id        UNIQUEIDENTIFIER PRIMARY KEY DEFAULT NEWID(),
    transaction_id UNIQUEIDENTIFIER NOT NULL,       -- reference into Cosmos
    account_id     VARCHAR(64)      NOT NULL,
    score          INT              NOT NULL,
    state_id       INT              NOT NULL REFERENCES case_states(state_id),
    opened_at      DATETIME2        NOT NULL DEFAULT SYSUTCDATETIME(),
    CONSTRAINT uq_cases_transaction UNIQUE (transaction_id)   -- idempotency: one case per transaction
);

CREATE INDEX ix_cases_state   ON cases(state_id);
CREATE INDEX ix_cases_account ON cases(account_id);

-- Case-analyst relationship
CREATE TABLE assignments (
    assignment_id UNIQUEIDENTIFIER PRIMARY KEY DEFAULT NEWID(),
    case_id       UNIQUEIDENTIFIER NOT NULL REFERENCES cases(case_id),
    analyst_id    VARCHAR(64)      NOT NULL,
    assigned_at   DATETIME2        NOT NULL DEFAULT SYSUTCDATETIME(),
    unassigned_at DATETIME2        NULL
);

-- Final decision on a case
CREATE TABLE resolutions (
    resolution_id UNIQUEIDENTIFIER PRIMARY KEY DEFAULT NEWID(),
    case_id       UNIQUEIDENTIFIER NOT NULL REFERENCES cases(case_id),
    decision      VARCHAR(32)      NOT NULL,        -- confirmed_fraud | false_positive
    analyst_id    VARCHAR(64)      NOT NULL,
    resolved_at   DATETIME2        NOT NULL DEFAULT SYSUTCDATETIME(),
    notes         NVARCHAR(1000)   NULL,
    CONSTRAINT uq_resolutions_case UNIQUE (case_id)  -- a case is resolved once
);

-- Immutable audit trail: what changed, who changed it, when.
-- No UPDATE or DELETE is ever issued against this table.
CREATE TABLE audit_log (
    audit_id    BIGINT IDENTITY(1,1) PRIMARY KEY,
    case_id     UNIQUEIDENTIFIER NOT NULL REFERENCES cases(case_id),
    from_state  INT              NULL REFERENCES case_states(state_id),
    to_state    INT              NOT NULL REFERENCES case_states(state_id),
    changed_by  VARCHAR(64)      NOT NULL,
    changed_at  DATETIME2        NOT NULL DEFAULT SYSUTCDATETIME(),
    reason      NVARCHAR(500)    NULL
);

CREATE INDEX ix_audit_case ON audit_log(case_id, changed_at);

-- Every state change writes an audit row automatically: the trail cannot be
-- bypassed by application code that forgets to log.
GO
CREATE TRIGGER trg_cases_audit ON cases AFTER UPDATE AS
BEGIN
    SET NOCOUNT ON;
    INSERT INTO audit_log (case_id, from_state, to_state, changed_by, reason)
    SELECT i.case_id, d.state_id, i.state_id, SUSER_SNAME(), 'state change'
    FROM inserted i
    JOIN deleted  d ON i.case_id = d.case_id
    WHERE i.state_id <> d.state_id;
END;
