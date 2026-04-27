-- =============================================================================
-- QUERIES DE CASOS DE USO — SISTEMA DE RESERVAS DELUXE
-- Motor: PostgreSQL 18
-- Convención: parámetros con $n para uso con asyncpg
-- =============================================================================


-- =============================================================================
-- CATÁLOGOS — DATOS INICIALES
-- =============================================================================

-- Registrar métodos de pago
INSERT INTO catalog.payment_methods (name)
VALUES ('nequi'), ('daviplata'), ('bancolombia')
ON CONFLICT DO NOTHING;

-- Verificar catálogos base necesarios
INSERT INTO catalog.type_users (name) VALUES ('admin'), ('customer')
ON CONFLICT DO NOTHING;

INSERT INTO catalog.reservation_states (name)
VALUES ('pending'), ('confirmed'), ('cancelled'), ('completed')
ON CONFLICT DO NOTHING;

INSERT INTO catalog.table_states (name)
VALUES ('available'), ('reserved'), ('occupied'), ('maintenance')
ON CONFLICT DO NOTHING;

INSERT INTO catalog.table_types (name)
VALUES ('standard'), ('vip'), ('private')
ON CONFLICT DO NOTHING;

INSERT INTO catalog.event_states (name)
VALUES ('draft'), ('published'), ('ongoing'), ('finished'), ('cancelled')
ON CONFLICT DO NOTHING;

INSERT INTO catalog.ticket_states (name)
VALUES ('active'), ('used'), ('cancelled'), ('expired'), ('pending')
ON CONFLICT DO NOTHING;


-- =============================================================================
-- CASO 1: CREACIÓN DE USUARIO
-- Parámetros: $1=username, $2=email, $3=phone_number, $4=telegram_id
-- Nota: type_user_id siempre es 'customer' al registrarse
-- =============================================================================

INSERT INTO core.users (username, type_user_id, email, phone_number, telegram_id)
VALUES (
    $1,
    (SELECT id FROM catalog.type_users WHERE name = 'customer'),
    $2,
    $3,
    $4
)
ON CONFLICT (telegram_id) DO UPDATE
    SET username     = EXCLUDED.username,
        updated_at   = CURRENT_TIMESTAMP
RETURNING id, username, email, telegram_id, created_at;


-- =============================================================================
-- CASO 2: CREACIÓN DE EVENTO
-- Parámetros: $1=name, $2=description, $3=start_time, $4=end_time
-- Estado inicial siempre: 'draft'
-- =============================================================================

INSERT INTO core.events (name, description, start_time, end_time, event_state_id)
VALUES (
    $1,
    $2,
    $3::TIMESTAMP,
    $4::TIMESTAMP,
    (SELECT id FROM catalog.event_states WHERE name = 'draft')
)
RETURNING id, name, start_time, end_time;


-- =============================================================================
-- CASO 3A: CREACIÓN DE MESA FÍSICA (sin precio)
-- Parámetros: $1=number, $2=table_type_name ('standard'|'vip'|'private'), $3=capacity
-- =============================================================================

INSERT INTO core.dico_tables (number, table_type_id, capacity, table_state_id)
VALUES (
    $1,
    (SELECT id FROM catalog.table_types WHERE name = $2),
    $3,
    (SELECT id FROM catalog.table_states WHERE name = 'available')
)
RETURNING id, number, capacity;


-- CREACIÓN DE MÚLTIPLES MESAS DEL MISMO TIPO EN SERIE
-- Parámetros: $1=numero_inicio, $2=numero_fin, $3=table_type_name, $4=capacity
INSERT INTO core.dico_tables (number, table_type_id, capacity, table_state_id)
SELECT
    gs,
    (SELECT id FROM catalog.table_types WHERE name = $3),
    $4,
    (SELECT id FROM catalog.table_states WHERE name = 'available')
FROM generate_series($1::INTEGER, $2::INTEGER) gs
RETURNING id, number, capacity;


-- =============================================================================
-- CASO 3B: ASIGNAR PRECIO A MESA PARA UN EVENTO ESPECÍFICO
-- Parámetros: $1=table_id, $2=event_id, $3=price
-- =============================================================================

INSERT INTO core.table_prices (table_id, event_id, price)
VALUES ($1, $2, $3)
ON CONFLICT ON CONSTRAINT uq_table_prices_table_event
DO UPDATE SET price = EXCLUDED.price
RETURNING id, table_id, event_id, price;


-- ASIGNAR PRECIO A TODAS LAS MESAS DE UN TIPO PARA UN EVENTO
-- Parámetros: $1=table_type_name, $2=event_id, $3=price
INSERT INTO core.table_prices (table_id, event_id, price)
SELECT dt.id, $2, $3
FROM core.dico_tables dt
JOIN catalog.table_types tt ON tt.id = dt.table_type_id
WHERE tt.name = $1
ON CONFLICT ON CONSTRAINT uq_table_prices_table_event
DO UPDATE SET price = EXCLUDED.price;


-- =============================================================================
-- CASO 4: CREACIÓN DE TYPE_TICKET (admin crea el tipo de ticket para un evento)
-- Parámetros: $1=name, $2=event_id, $3=available_quantity, $4=price
-- max_override es NULL por defecto (sin override inicial)
-- =============================================================================

INSERT INTO core.type_tickets (name, event_id, available_quantity, price)
VALUES ($1, $2, $3, $4)
RETURNING id, name, event_id, available_quantity, price;


-- =============================================================================
-- CASO 5: CREACIÓN DE TICKET VENDIDO (cliente compra un ticket)
-- Parámetros: $1=user_id, $2=type_ticket_id
-- Estado inicial: 'pending' hasta que se apruebe el pago
-- Incluye validación de cupo con FOR UPDATE (control de concurrencia)
-- =============================================================================

-- Paso 1: Validar cupo disponible (debe estar dentro de una transacción)
SELECT
    tt.id,
    tt.available_quantity,
    tt.max_override,
    COALESCE(tt.max_override, tt.available_quantity) AS cupo_efectivo,
    COUNT(t.id) FILTER (
        WHERE t.ticket_state_id != (
            SELECT id FROM catalog.ticket_states WHERE name = 'cancelled'
        )
    ) AS vendidos
FROM core.type_tickets tt
LEFT JOIN transactions.tickets t ON t.type_ticket_id = tt.id
WHERE tt.id = $2
GROUP BY tt.id, tt.available_quantity, tt.max_override
FOR UPDATE;
-- Si vendidos >= cupo_efectivo → rechazar en el backend

-- Paso 2: Insertar el ticket
INSERT INTO transactions.tickets (user_id, type_ticket_id, ticket_state_id)
VALUES (
    $1,
    $2,
    (SELECT id FROM catalog.ticket_states WHERE name = 'pending')
)
RETURNING id, user_id, type_ticket_id, ticket_state_id, created_at;


-- =============================================================================
-- CASO 6: CREACIÓN DE RESERVACIÓN
-- Parámetros: $1=user_id, $2=table_id, $3=event_id (NULL si no hay evento)
-- Estado inicial: 'pending' hasta que se apruebe el pago
-- Incluye cálculo de expires_at (6:00am del día siguiente o del mismo día)
-- =============================================================================

-- Paso 1: Validar que la mesa esté disponible (FOR UPDATE)
SELECT id, table_state_id
FROM core.dico_tables
WHERE id = $2
  AND table_state_id = (SELECT id FROM catalog.table_states WHERE name = 'available')
FOR UPDATE;
-- Si no retorna fila → mesa no disponible → rechazar en el backend

-- Paso 2: Crear la reservación
INSERT INTO transactions.reservations (
    reservation_state_id,
    user_id,
    table_id,
    event_id,
    expires_at
)
VALUES (
    (SELECT id FROM catalog.reservation_states WHERE name = 'pending'),
    $1,
    $2,
    $3,
    -- expires_at: 6am del mismo día si es madrugada, 6am del día siguiente si es tarde
    CASE
        WHEN CURRENT_TIME < TIME '06:00:00'
        THEN DATE_TRUNC('day', CURRENT_TIMESTAMP) + INTERVAL '6 hours'
        ELSE DATE_TRUNC('day', CURRENT_TIMESTAMP) + INTERVAL '1 day' + INTERVAL '6 hours'
    END
)
RETURNING id, reservation_state_id, table_id, event_id, expires_at;

-- Paso 3: Marcar la mesa como reservada
UPDATE core.dico_tables
SET table_state_id = (SELECT id FROM catalog.table_states WHERE name = 'reserved')
WHERE id = $2;


-- =============================================================================
-- CASO 7: CREACIÓN DE ORDEN
-- Parámetros: $1=user_id
-- total inicia en 0 y se actualiza después de agregar los order_details
-- =============================================================================

INSERT INTO transactions.orders (user_id, total, status)
VALUES ($1, 0, 'pending')
RETURNING id, user_id, ordered_at, total, status;


-- =============================================================================
-- CASO 8: CREACIÓN DE ORDER_DETAIL
-- Dos variantes: línea de ticket o línea de reserva (nunca ambos)
-- =============================================================================

-- Variante A: línea de ticket
-- Parámetros: $1=order_id, $2=ticket_id, $3=unit_price, $4=discount (0 si no hay)
INSERT INTO transactions.order_details (order_id, ticket_id, quantity, unit_price, discount)
VALUES ($1, $2, 1, $3, $4)
RETURNING id, order_id, ticket_id, unit_price, discount,
          (unit_price - discount) * quantity AS subtotal;

-- Variante B: línea de reserva
-- Parámetros: $1=order_id, $2=reservation_id, $3=unit_price, $4=discount
INSERT INTO transactions.order_details (order_id, reservation_id, quantity, unit_price, discount)
VALUES ($1, $2, 1, $3, $4)
RETURNING id, order_id, reservation_id, unit_price, discount,
          (unit_price - discount) * quantity AS subtotal;

-- Actualizar el total de la orden después de insertar todos los detalles
-- Parámetros: $1=order_id
UPDATE transactions.orders
SET total = (
    SELECT COALESCE(SUM((unit_price - discount) * quantity), 0)
    FROM transactions.order_details
    WHERE order_id = $1
)
WHERE id = $1
RETURNING id, total;


-- =============================================================================
-- CASO 9: CREACIÓN DE PAGO
-- Parámetros: $1=order_id, $2=payment_method_name, $3=amount,
--             $4=voucher_url, $5=reference_number
-- Estado inicial: 'pending' hasta verificación del admin
-- =============================================================================

-- Validar que el reference_number no haya sido usado antes (antiduplicado)
SELECT id FROM transactions.payments
WHERE reference_number = $5
FOR UPDATE;
-- Si retorna fila → comprobante duplicado → rechazar en el backend

-- Insertar el pago
INSERT INTO transactions.payments (
    payment_method_id,
    amount,
    order_id,
    status,
    voucher_url,
    reference_number
)
VALUES (
    (SELECT id FROM catalog.payment_methods WHERE name = $2),
    $3,
    $1,
    'pending',
    $4,
    $5
)
RETURNING id, order_id, amount, status, created_at;


-- =============================================================================
-- CASO 10: CANCELACIÓN DE RESERVACIÓN
-- Parámetros: $1=reservation_id, $2=user_id (para validar pertenencia)
-- =============================================================================

-- Paso 1: Validar que la reserva existe, pertenece al usuario y está activa
SELECT id, table_id, reservation_state_id
FROM transactions.reservations
WHERE id = $1
  AND user_id = $2
  AND reservation_state_id IN (
      SELECT id FROM catalog.reservation_states
      WHERE name IN ('pending', 'confirmed')
  )
FOR UPDATE;
-- Si no retorna fila → reserva no existe, no pertenece al usuario o ya está cancelada

-- Paso 2: Cancelar la reserva
UPDATE transactions.reservations
SET reservation_state_id = (
    SELECT id FROM catalog.reservation_states WHERE name = 'cancelled'
)
WHERE id = $1
RETURNING id, table_id, reservation_state_id;

-- Paso 3: Liberar la mesa
UPDATE core.dico_tables
SET table_state_id = (SELECT id FROM catalog.table_states WHERE name = 'available')
WHERE id = (
    SELECT table_id FROM transactions.reservations WHERE id = $1
);


-- =============================================================================
-- CASO 11: CANCELACIÓN DE EVENTO
-- Parámetros: $1=event_id
-- Efecto en cascada: cancela reservas, tickets y libera mesas
-- El trigger trg_release_tables_on_event_end maneja la liberación de mesas
-- automáticamente al cambiar el estado
-- =============================================================================

-- Paso 1: Bloquear el evento
SELECT id, event_state_id
FROM core.events
WHERE id = $1
  AND event_state_id NOT IN (
      SELECT id FROM catalog.event_states WHERE name IN ('cancelled', 'finished')
  )
FOR UPDATE;
-- Si no retorna fila → evento no existe o ya está cancelado/finalizado

-- Paso 2: Cancelar tickets activos del evento
UPDATE transactions.tickets
SET ticket_state_id = (SELECT id FROM catalog.ticket_states WHERE name = 'cancelled')
WHERE type_ticket_id IN (
    SELECT id FROM core.type_tickets WHERE event_id = $1
)
AND ticket_state_id IN (
    SELECT id FROM catalog.ticket_states WHERE name IN ('active', 'pending')
);

-- Paso 3: Cancelar reservas activas del evento
UPDATE transactions.reservations
SET reservation_state_id = (
    SELECT id FROM catalog.reservation_states WHERE name = 'cancelled'
)
WHERE event_id = $1
  AND reservation_state_id IN (
      SELECT id FROM catalog.reservation_states WHERE name IN ('pending', 'confirmed')
  );

-- Paso 4: Cambiar estado del evento a cancelled
-- El trigger fn_release_tables_on_event_end se dispara aquí
-- y libera las mesas automáticamente
UPDATE core.events
SET event_state_id = (SELECT id FROM catalog.event_states WHERE name = 'cancelled')
WHERE id = $1
RETURNING id, name, event_state_id;


-- =============================================================================
-- CASO 12: APROBACIÓN DE ORDEN (admin aprueba el pago)
-- Parámetros: $1=order_id
-- Activa tickets y confirma reservas asociadas
-- =============================================================================

-- Paso 1: Bloquear la orden
SELECT id, status FROM transactions.orders
WHERE id = $1 AND status = 'pending'
FOR UPDATE;

-- Paso 2: Activar tickets pendientes de la orden
UPDATE transactions.tickets
SET ticket_state_id = (SELECT id FROM catalog.ticket_states WHERE name = 'active')
WHERE id IN (
    SELECT ticket_id FROM transactions.order_details
    WHERE order_id = $1 AND ticket_id IS NOT NULL
)
AND ticket_state_id = (SELECT id FROM catalog.ticket_states WHERE name = 'pending');

-- Paso 3: Confirmar reservas pendientes de la orden
UPDATE transactions.reservations
SET reservation_state_id = (
    SELECT id FROM catalog.reservation_states WHERE name = 'confirmed'
)
WHERE id IN (
    SELECT reservation_id FROM transactions.order_details
    WHERE order_id = $1 AND reservation_id IS NOT NULL
)
AND reservation_state_id = (
    SELECT id FROM catalog.reservation_states WHERE name = 'pending'
);

-- Paso 4: Aprobar el pago
UPDATE transactions.payments
SET status = 'verified'
WHERE order_id = $1 AND status = 'pending';

-- Paso 5: Cambiar estado de la orden a approved
UPDATE transactions.orders
SET status = 'approved', updated_at = CURRENT_TIMESTAMP
WHERE id = $1
RETURNING id, status, total;


-- =============================================================================
-- CASO 13: VALIDAR ENTRADA AL EVENTO (staff escanea ticket en la puerta)
-- Parámetros: $1=ticket_id
-- =============================================================================

-- Paso 1: Validar ticket activo y evento en curso
SELECT t.id, t.user_id, tt.event_id
FROM transactions.tickets t
JOIN core.type_tickets tt ON tt.id = t.type_ticket_id
JOIN core.events e ON e.id = tt.event_id
WHERE t.id = $1
  AND t.ticket_state_id = (SELECT id FROM catalog.ticket_states WHERE name = 'active')
  AND e.event_state_id  = (SELECT id FROM catalog.event_states WHERE name = 'ongoing')
FOR UPDATE;
-- Si no retorna fila → ticket inválido, ya usado, o evento no está en curso

-- Paso 2: Marcar ticket como usado
UPDATE transactions.tickets
SET ticket_state_id = (SELECT id FROM catalog.ticket_states WHERE name = 'used'),
    updated_at      = CURRENT_TIMESTAMP
WHERE id = $1
RETURNING id, ticket_state_id;

-- Paso 3: Marcar mesa como ocupada si tenía reserva confirmada
UPDATE core.dico_tables
SET table_state_id = (SELECT id FROM catalog.table_states WHERE name = 'occupied')
WHERE id = (
    SELECT r.table_id
    FROM transactions.reservations r
    JOIN transactions.tickets t ON t.user_id = r.user_id
    JOIN core.type_tickets tt ON tt.id = t.type_ticket_id
    WHERE t.id = $1
      AND r.event_id = tt.event_id
      AND r.reservation_state_id = (
          SELECT id FROM catalog.reservation_states WHERE name = 'confirmed'
      )
    LIMIT 1
);


-- =============================================================================
-- CASOS DE USO FALTANTES DETECTADOS
-- Los siguientes casos son necesarios para completar el ciclo del negocio
-- =============================================================================

-- CASO 14: CONSULTAR DISPONIBILIDAD DE MESAS POR TIPO Y EVENTO
-- Parámetros: $1=event_id, $2=table_type_name
SELECT
    dt.id,
    dt.number,
    dt.capacity,
    tt.name AS tipo,
    tp.price
FROM core.dico_tables dt
JOIN catalog.table_types tt ON tt.id = dt.table_type_id
JOIN catalog.table_states ts ON ts.id = dt.table_state_id
LEFT JOIN core.table_prices tp
    ON tp.table_id = dt.id AND tp.event_id = $1
WHERE tt.name = $2
  AND ts.name = 'available'
ORDER BY dt.number;


-- CASO 15: CONSULTAR TIPOS DE TICKET DISPONIBLES PARA UN EVENTO
-- Parámetros: $1=event_id
SELECT
    tt.id,
    tt.name,
    tt.price,
    COALESCE(tt.max_override, tt.available_quantity) AS cupo_total,
    COALESCE(tt.max_override, tt.available_quantity)
        - COUNT(t.id) FILTER (
            WHERE t.ticket_state_id != (
                SELECT id FROM catalog.ticket_states WHERE name = 'cancelled'
            )
          ) AS disponibles
FROM core.type_tickets tt
LEFT JOIN transactions.tickets t ON t.type_ticket_id = tt.id
WHERE tt.event_id = $1
GROUP BY tt.id, tt.name, tt.price, tt.available_quantity, tt.max_override
HAVING
    COALESCE(tt.max_override, tt.available_quantity)
        - COUNT(t.id) FILTER (
            WHERE t.ticket_state_id != (
                SELECT id FROM catalog.ticket_states WHERE name = 'cancelled'
            )
          ) > 0
ORDER BY tt.price;


-- CASO 16: CONSULTAR HISTORIAL DE ÓRDENES DE UN USUARIO
-- Parámetros: $1=telegram_id
SELECT
    o.id                AS order_id,
    o.ordered_at,
    o.total,
    o.status,
    tt_name.name        AS tipo_ticket,
    ts_name.name        AS estado_ticket,
    dt.number           AS numero_mesa,
    tbl.name            AS tipo_mesa,
    rs.name             AS estado_reserva,
    od.unit_price,
    od.discount,
    (od.unit_price - od.discount) * od.quantity AS subtotal
FROM transactions.orders o
JOIN core.users u ON u.id = o.user_id
JOIN transactions.order_details od ON od.order_id = o.id
LEFT JOIN transactions.tickets tk ON tk.id = od.ticket_id
LEFT JOIN core.type_tickets tt_name ON tt_name.id = tk.type_ticket_id
LEFT JOIN catalog.ticket_states ts_name ON ts_name.id = tk.ticket_state_id
LEFT JOIN transactions.reservations r ON r.id = od.reservation_id
LEFT JOIN core.dico_tables dt ON dt.id = r.table_id
LEFT JOIN catalog.table_types tbl ON tbl.id = dt.table_type_id
LEFT JOIN catalog.reservation_states rs ON rs.id = r.reservation_state_id
WHERE u.telegram_id = $1
ORDER BY o.ordered_at DESC;


-- CASO 17: CAMBIAR ESTADO DEL EVENTO (publicar, iniciar, finalizar)
-- Parámetros: $1=event_id, $2=new_state_name
-- Transiciones válidas controladas en el backend:
-- draft → published → ongoing → finished, cualquiera → cancelled
UPDATE core.events
SET event_state_id = (SELECT id FROM catalog.event_states WHERE name = $2),
    updated_at     = CURRENT_TIMESTAMP
WHERE id = $1
RETURNING id, name, event_state_id;


-- CASO 18: EXPIRAR TICKETS NO USADOS AL FINALIZAR EVENTO
-- Parámetros: $1=event_id
UPDATE transactions.tickets
SET ticket_state_id = (SELECT id FROM catalog.ticket_states WHERE name = 'expired'),
    updated_at      = CURRENT_TIMESTAMP
WHERE type_ticket_id IN (
    SELECT id FROM core.type_tickets WHERE event_id = $1
)
AND ticket_state_id = (SELECT id FROM catalog.ticket_states WHERE name = 'active');


-- CASO 19: REPORTE DE RECAUDACIÓN POR EVENTO
-- Parámetros: $1=event_id
SELECT
    e.name                              AS evento,
    COUNT(DISTINCT o.id)                AS total_ordenes,
    COUNT(DISTINCT tk.id) FILTER (
        WHERE tt.event_id = e.id
    )                                   AS tickets_vendidos,
    COUNT(DISTINCT r.id) FILTER (
        WHERE r.event_id = e.id
    )                                   AS mesas_reservadas,
    COALESCE(SUM(p.amount), 0)          AS total_recaudado
FROM core.events e
LEFT JOIN core.type_tickets tt ON tt.event_id = e.id
LEFT JOIN transactions.tickets tk ON tk.type_ticket_id = tt.id
LEFT JOIN transactions.order_details od ON od.ticket_id = tk.id
LEFT JOIN transactions.orders o ON o.id = od.order_id
LEFT JOIN transactions.payments p ON p.order_id = o.id AND p.status = 'verified'
LEFT JOIN transactions.reservations r ON r.event_id = e.id
WHERE e.id = $1
GROUP BY e.name, e.id;


-- CASO 20: LIBERAR MESAS EXPIRADAS (job APScheduler cada 10 minutos)
-- Sin parámetros — corre sobre todas las reservas expiradas
BEGIN;

UPDATE core.dico_tables
SET table_state_id = (SELECT id FROM catalog.table_states WHERE name = 'available')
WHERE id IN (
    SELECT table_id FROM transactions.reservations
    WHERE expires_at < CURRENT_TIMESTAMP
      AND expires_at IS NOT NULL
      AND reservation_state_id = (
          SELECT id FROM catalog.reservation_states WHERE name = 'confirmed'
      )
);

UPDATE transactions.reservations
SET reservation_state_id = (
    SELECT id FROM catalog.reservation_states WHERE name = 'completed'
)
WHERE expires_at < CURRENT_TIMESTAMP
  AND expires_at IS NOT NULL
  AND reservation_state_id = (
      SELECT id FROM catalog.reservation_states WHERE name = 'confirmed'
  );

COMMIT;