
CREATE TRIGGER trg_release_tables_on_event_end
  AFTER UPDATE ON core.events
  FOR EACH ROW EXECUTE FUNCTION core.fn_release_tables_on_event_end(); que hace este trigger



CREATE TRIGGER trg_users_updated_at
  BEFORE UPDATE ON core.users
  FOR EACH ROW EXECUTE FUNCTION core.fn_set_updated_at();

CREATE TRIGGER trg_events_updated_at
  BEFORE UPDATE ON core.events
  FOR EACH ROW EXECUTE FUNCTION core.fn_set_updated_at();


CREATE TRIGGER trg_orders_updated_at
  BEFORE UPDATE ON transactions.orders
  FOR EACH ROW EXECUTE FUNCTION core.fn_set_updated_at();

CREATE TRIGGER trg_reservations_updated_at
  BEFORE UPDATE ON transactions.reservations
  FOR EACH ROW EXECUTE FUNCTION core.fn_set_updated_at();



CREATE TRIGGER trg_tickets_updated_at
  BEFORE UPDATE ON transactions.tickets
  FOR EACH ROW EXECUTE FUNCTION core.fn_set_updated_at();



CREATE TRIGGER trg_audit_reservations
  AFTER INSERT OR UPDATE OR DELETE ON transactions.reservations
  FOR EACH ROW EXECUTE FUNCTION audit.fn_audit_log();

CREATE TRIGGER trg_audit_orders
  AFTER INSERT OR UPDATE OR DELETE ON transactions.orders
  FOR EACH ROW EXECUTE FUNCTION audit.fn_audit_log();


CREATE TRIGGER trg_audit_payments
  AFTER INSERT OR UPDATE OR DELETE ON transactions.payments
  FOR EACH ROW EXECUTE FUNCTION audit.fn_audit_log();


CREATE TRIGGER trg_audit_tickets
  AFTER INSERT OR UPDATE OR DELETE ON transactions.tickets
  FOR EACH ROW EXECUTE FUNCTION audit.fn_audit_log();