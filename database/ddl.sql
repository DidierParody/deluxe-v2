-- =============================================================================
-- DDL COMPLETO — SISTEMA DE RESERVAS DELUXE
-- Generado desde Neon para importar en DiagramDB
-- =============================================================================

-- =============================================================================
-- SCHEMA: catalog
-- =============================================================================

CREATE SCHEMA catalog
CREATE SCHEMA core
CREATE SCHEMA transactions
CREATE SCHEMA system
CREATE SCHEMA audit


CREATE TABLE catalog.type_users (
    id      INTEGER NOT NULL,
    name    VARCHAR(100) NOT NULL,
    CONSTRAINT type_users_pkey PRIMARY KEY (id)
);

CREATE TABLE catalog.event_states (
    id      INTEGER NOT NULL,
    name    VARCHAR(100) NOT NULL,
    CONSTRAINT event_states_pkey PRIMARY KEY (id)
);

CREATE TABLE catalog.reservation_states (
    id      INTEGER NOT NULL,
    name    VARCHAR(100) NOT NULL,
    CONSTRAINT reservation_states_pkey PRIMARY KEY (id)
);

CREATE TABLE catalog.table_states (
    id      INTEGER NOT NULL,
    name    VARCHAR(100) NOT NULL,
    CONSTRAINT table_states_pkey PRIMARY KEY (id)
);

CREATE TABLE catalog.table_types (
    id      INTEGER NOT NULL,
    name    VARCHAR(100) NOT NULL,
    CONSTRAINT table_types_pkey PRIMARY KEY (id)
);

CREATE TABLE catalog.ticket_states (
    id      INTEGER NOT NULL,
    name    VARCHAR(100) NOT NULL,
    CONSTRAINT ticket_states_pkey PRIMARY KEY (id)
);

CREATE TABLE catalog.payment_methods (
    id      INTEGER NOT NULL,
    name    VARCHAR(100) NOT NULL,
    CONSTRAINT payment_methods_pkey PRIMARY KEY (id)
);


-- =============================================================================
-- SCHEMA: core
-- =============================================================================

CREATE TABLE core.users (
    id              INTEGER NOT NULL,
    username        VARCHAR(255) NOT NULL,
    type_user_id    INTEGER NOT NULL,
    email           VARCHAR(255) NOT NULL,
    phone_number    VARCHAR(50) NOT NULL,
    created_at      TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at      TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    telegram_id     BIGINT UNIQUE,
    CONSTRAINT users_pkey PRIMARY KEY (id),
    CONSTRAINT users_email_key UNIQUE (email),
    CONSTRAINT users_phone_number_key UNIQUE (phone_number),
    CONSTRAINT users_telegram_id_key UNIQUE (telegram_id),
    CONSTRAINT chk_users_email_format CHECK (email ~ '^[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}$'),
    CONSTRAINT chk_users_created_at CHECK (created_at <= CURRENT_TIMESTAMP)
);

CREATE TABLE core.events (
    id              INTEGER NOT NULL,
    name            VARCHAR(300) NOT NULL,
    description     TEXT,
    start_time      TIMESTAMP NOT NULL,
    end_time        TIMESTAMP NOT NULL,
    event_state_id  INTEGER,
    created_at      TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at      TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT events_pkey PRIMARY KEY (id),
    CONSTRAINT chk_events_time_range CHECK (start_time < end_time)
);

CREATE TABLE core.dico_tables (
    id              INTEGER NOT NULL,
    number          INTEGER NOT NULL,
    table_type_id   INTEGER NOT NULL,
    capacity        INTEGER NOT NULL,
    table_state_id  INTEGER NOT NULL,
    CONSTRAINT dico_tables_pkey PRIMARY KEY (id),
    CONSTRAINT dico_tables_number_key UNIQUE (number)
);

CREATE TABLE core.type_tickets (
    id                  INTEGER NOT NULL,
    name                VARCHAR(200),
    event_id            INTEGER,
    available_quantity  INTEGER NOT NULL,
    max_override        INTEGER,
    price               NUMERIC(10,2) NOT NULL,
    CONSTRAINT type_tickets_pkey PRIMARY KEY (id),
    CONSTRAINT chk_type_tickets_override CHECK (max_override IS NULL OR max_override > available_quantity)
);

CREATE TABLE core.table_prices (
    id          INTEGER NOT NULL,
    table_id    INTEGER NOT NULL,
    event_id    INTEGER NOT NULL,
    price       NUMERIC(10,2) NOT NULL,
    CONSTRAINT table_prices_pkey PRIMARY KEY (id),
    CONSTRAINT uq_table_prices_table_event UNIQUE (table_id, event_id)
);


-- =============================================================================
-- SCHEMA: transactions
-- =============================================================================

CREATE TABLE transactions.orders (
    id          INTEGER NOT NULL,
    user_id     INTEGER NOT NULL,
    ordered_at  TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    total       NUMERIC(10,2) NOT NULL DEFAULT 0,
    created_at  TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at  TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    status      VARCHAR(20) DEFAULT 'pending',
    admin_msg_id BIGINT,
    CONSTRAINT orders_pkey PRIMARY KEY (id),
    CONSTRAINT chk_orders_total CHECK (total >= 0)
);

CREATE TABLE transactions.reservations (
    id                      INTEGER NOT NULL,
    reservation_state_id    INTEGER NOT NULL,
    user_id                 INTEGER NOT NULL,
    reserved_at             TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    table_id                INTEGER NOT NULL,
    event_id                INTEGER,
    created_at              TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at              TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    expires_at              TIMESTAMP,
    CONSTRAINT reservations_pkey PRIMARY KEY (id)
);

CREATE TABLE transactions.tickets (
    id                  INTEGER NOT NULL,
    user_id             INTEGER NOT NULL,
    type_ticket_id      INTEGER NOT NULL,
    ticket_state_id     INTEGER NOT NULL,
    created_at          TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at          TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT tickets_pkey PRIMARY KEY (id)
);

CREATE TABLE transactions.order_details (
    id              INTEGER NOT NULL,
    order_id        INTEGER NOT NULL,
    ticket_id       INTEGER,
    reservation_id  INTEGER,
    quantity        INTEGER NOT NULL DEFAULT 1,
    unit_price      NUMERIC(10,2) NOT NULL,
    discount        NUMERIC(10,2) NOT NULL DEFAULT 0,
    type_ticket_id  INTEGER,
    table_id        INTEGER,
    CONSTRAINT order_details_pkey PRIMARY KEY (id),
    CONSTRAINT chk_order_details_discount CHECK (discount >= 0)
);

CREATE TABLE transactions.payments (
    id                  INTEGER NOT NULL,
    payment_method_id   INTEGER NOT NULL,
    amount              NUMERIC(10,2) NOT NULL,
    order_id            INTEGER NOT NULL,
    created_at          TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    status              TEXT DEFAULT 'pending',
    voucher_url         TEXT,
    reference_number    TEXT,
    CONSTRAINT payments_pkey PRIMARY KEY (id),
    CONSTRAINT chk_payments_amount CHECK (amount >= 0)
);


-- =============================================================================
-- SCHEMA: audit
-- =============================================================================

CREATE TABLE audit.audit_logs (
    id              BIGINT NOT NULL,
    table_name      VARCHAR(100) NOT NULL,
    record_id       INTEGER NOT NULL,
    action          VARCHAR(10) NOT NULL,
    old_data        JSONB,
    new_data        JSONB,
    user_id         INTEGER,
    performed_at    TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT audit_logs_pkey PRIMARY KEY (id),
    CONSTRAINT audit_logs_action_check CHECK (action IN ('INSERT', 'UPDATE', 'DELETE'))
);


-- =============================================================================
-- SCHEMA: system
-- =============================================================================

CREATE TABLE system.pairing_codes (
    id          INTEGER NOT NULL,
    code        TEXT NOT NULL,
    telegram_id BIGINT NOT NULL,
    expires_at  TIMESTAMP NOT NULL,
    created_at  TIMESTAMP DEFAULT now(),
    CONSTRAINT pairing_codes_pkey PRIMARY KEY (id)
);

CREATE TABLE system.admin_actions_log (
    id          INTEGER NOT NULL,
    admin_id    BIGINT NOT NULL,
    action      TEXT NOT NULL,
    payload     JSONB,
    ip_address  TEXT,
    user_agent  TEXT,
    created_at  TIMESTAMP DEFAULT now(),
    CONSTRAINT admin_actions_log_pkey PRIMARY KEY (id)
);


-- =============================================================================
-- FOREIGN KEYS
-- =============================================================================

-- core
ALTER TABLE core.users
    ADD CONSTRAINT fk_users_type_user
    FOREIGN KEY (type_user_id) REFERENCES catalog.type_users(id);

ALTER TABLE core.events
    ADD CONSTRAINT fk_events_state
    FOREIGN KEY (event_state_id) REFERENCES catalog.event_states(id);

ALTER TABLE core.dico_tables
    ADD CONSTRAINT fk_tables_type
    FOREIGN KEY (table_type_id) REFERENCES catalog.table_types(id);

ALTER TABLE core.dico_tables
    ADD CONSTRAINT fk_tables_state
    FOREIGN KEY (table_state_id) REFERENCES catalog.table_states(id);

ALTER TABLE core.type_tickets
    ADD CONSTRAINT fk_type_tickets_event
    FOREIGN KEY (event_id) REFERENCES core.events(id);

ALTER TABLE core.table_prices
    ADD CONSTRAINT fk_table_prices_table
    FOREIGN KEY (table_id) REFERENCES core.dico_tables(id);

ALTER TABLE core.table_prices
    ADD CONSTRAINT fk_table_prices_event
    FOREIGN KEY (event_id) REFERENCES core.events(id);

-- transactions
ALTER TABLE transactions.orders
    ADD CONSTRAINT fk_orders_user
    FOREIGN KEY (user_id) REFERENCES core.users(id);

ALTER TABLE transactions.reservations
    ADD CONSTRAINT fk_reservations_user
    FOREIGN KEY (user_id) REFERENCES core.users(id);

ALTER TABLE transactions.reservations
    ADD CONSTRAINT fk_reservations_state
    FOREIGN KEY (reservation_state_id) REFERENCES catalog.reservation_states(id);

ALTER TABLE transactions.reservations
    ADD CONSTRAINT fk_reservations_table
    FOREIGN KEY (table_id) REFERENCES core.dico_tables(id);

ALTER TABLE transactions.reservations
    ADD CONSTRAINT fk_reservations_event
    FOREIGN KEY (event_id) REFERENCES core.events(id);

ALTER TABLE transactions.tickets
    ADD CONSTRAINT fk_tickets_user
    FOREIGN KEY (user_id) REFERENCES core.users(id);

ALTER TABLE transactions.tickets
    ADD CONSTRAINT fk_tickets_type
    FOREIGN KEY (type_ticket_id) REFERENCES core.type_tickets(id);

ALTER TABLE transactions.tickets
    ADD CONSTRAINT fk_tickets_state
    FOREIGN KEY (ticket_state_id) REFERENCES catalog.ticket_states(id);

ALTER TABLE transactions.order_details
    ADD CONSTRAINT fk_order_details_order
    FOREIGN KEY (order_id) REFERENCES transactions.orders(id);

ALTER TABLE transactions.order_details
    ADD CONSTRAINT fk_order_details_ticket
    FOREIGN KEY (ticket_id) REFERENCES transactions.tickets(id);

ALTER TABLE transactions.order_details
    ADD CONSTRAINT fk_order_details_reservation
    FOREIGN KEY (reservation_id) REFERENCES transactions.reservations(id);

ALTER TABLE transactions.payments
    ADD CONSTRAINT fk_payments_order
    FOREIGN KEY (order_id) REFERENCES transactions.orders(id);

ALTER TABLE transactions.payments
    ADD CONSTRAINT fk_payments_method
    FOREIGN KEY (payment_method_id) REFERENCES catalog.payment_methods(id);


-- =============================================================================
-- ÍNDICES
-- =============================================================================

CREATE INDEX idx_users_type_user ON core.users(type_user_id);
CREATE INDEX idx_type_tickets_event ON core.type_tickets(event_id);
CREATE INDEX idx_table_prices_table ON core.table_prices(table_id);
CREATE INDEX idx_table_prices_event ON core.table_prices(event_id);
CREATE INDEX idx_reservations_user ON transactions.reservations(user_id);
CREATE INDEX idx_reservations_table ON transactions.reservations(table_id);
CREATE INDEX idx_reservations_event ON transactions.reservations(event_id);
CREATE INDEX idx_reservations_state ON transactions.reservations(reservation_state_id);
CREATE INDEX idx_tickets_user ON transactions.tickets(user_id);
CREATE INDEX idx_tickets_type ON transactions.tickets(type_ticket_id);
CREATE INDEX idx_tickets_state ON transactions.tickets(ticket_state_id);
CREATE INDEX idx_orders_user ON transactions.orders(user_id);
CREATE INDEX idx_order_details_order ON transactions.order_details(order_id);
CREATE INDEX idx_order_details_ticket ON transactions.order_details(ticket_id);
CREATE INDEX idx_order_details_reservation ON transactions.order_details(reservation_id);
CREATE INDEX idx_payments_order ON transactions.payments(order_id);
CREATE INDEX idx_audit_logs_table_record ON audit.audit_logs(table_name, record_id);
CREATE INDEX idx_audit_logs_performed_at ON audit.audit_logs(performed_at DESC);
CREATE UNIQUE INDEX uq_active_reservation_per_table ON transactions.reservations(table_id)
    WHERE reservation_state_id NOT IN (3, 4);


