
CREATE OR REPLACE FUNCTION core.fn_release_tables_on_event_end()
RETURNS TRIGGER AS $$
BEGIN
  IF NEW.event_state_id IN (
    SELECT id FROM catalog.event_states 
    WHERE name IN ('finished', 'cancelled')
  ) AND OLD.event_state_id != NEW.event_state_id THEN
    
    UPDATE core.dico_tables
    SET table_state_id = (
      SELECT id FROM catalog.table_states WHERE name = 'available'
    )
    WHERE id IN (
      SELECT table_id FROM transactions.reservations
      WHERE event_id = NEW.id
      AND reservation_state_id IN (
        SELECT id FROM catalog.reservation_states 
        WHERE name IN ('confirmed', 'pending')
      )
    );

  END IF;
  RETURN NEW;
END;
$$ LANGUAGE plpgsql;




CREATE OR REPLACE FUNCTION core.fn_set_updated_at()
RETURNS TRIGGER AS $$
BEGIN
  NEW.updated_at = CURRENT_TIMESTAMP;
  RETURN NEW;
END;
$$ LANGUAGE plpgsql;



CREATE OR REPLACE FUNCTION audit.fn_audit_log()
RETURNS TRIGGER AS $$
BEGIN
  IF TG_OP = 'INSERT' THEN
    INSERT INTO audit.audit_logs (table_name, record_id, action, new_data)
    VALUES (TG_TABLE_NAME, NEW.id, 'INSERT', to_jsonb(NEW));

  ELSIF TG_OP = 'UPDATE' THEN
    INSERT INTO audit.audit_logs (table_name, record_id, action, old_data, new_data)
    VALUES (TG_TABLE_NAME, NEW.id, 'UPDATE', to_jsonb(OLD), to_jsonb(NEW));

  ELSIF TG_OP = 'DELETE' THEN
    INSERT INTO audit.audit_logs (table_name, record_id, action, old_data)
    VALUES (TG_TABLE_NAME, OLD.id, 'DELETE', to_jsonb(OLD));
  END IF;

  RETURN NULL;
END;
$$ LANGUAGE plpgsql
SECURITY DEFINER;

